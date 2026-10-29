import json
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import Cart, CartItem, Category, Order, OrderItem, Payment, Product
from .serializers import cart_data, category_data, order_data, product_data


DELIVERY_FEE = 100
MAX_PRESCRIPTION_SIZE = 5 * 1024 * 1024


def _prescription_error(upload):
    if upload.size > MAX_PRESCRIPTION_SIZE:
        return "Prescription files must be 5 MB or smaller."
    suffix = Path(upload.name).suffix.lower()
    signature = upload.read(8)
    upload.seek(0)
    valid = {
        ".pdf": signature.startswith(b"%PDF-"),
        ".jpg": signature.startswith(b"\xff\xd8\xff"),
        ".jpeg": signature.startswith(b"\xff\xd8\xff"),
        ".png": signature.startswith(b"\x89PNG\r\n\x1a\n"),
    }
    if not valid.get(suffix, False):
        return "Upload a valid PDF, JPG, or PNG prescription (maximum 5 MB)."
    return ""


def _body(request):
    try:
        return json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def _cart_for(user):
    return Cart.objects.get_or_create(user=user)[0]


def _filtered_products(request):
    products = Product.objects.filter(is_active=True).select_related("category")
    search = request.GET.get("search", "").strip()
    category = request.GET.get("category", "").strip()
    product_type = request.GET.get("type", "").strip()
    availability = request.GET.get("availability", "").strip()
    prescription = request.GET.get("prescription", "").strip()
    if search:
        products = products.filter(Q(name__icontains=search) | Q(description__icontains=search) | Q(strength__icontains=search) | Q(category__name__icontains=search))
    if category and category.lower() not in {"all", "all-conditions"}:
        products = products.filter(Q(category__slug__iexact=category) | Q(category__name__iexact=category))
    if product_type and product_type.lower() != "all":
        products = products.filter(strength__iendswith=f"- {product_type}")
    if availability == "in_stock":
        products = products.filter(stock_quantity__gt=0)
    elif availability == "out_of_stock":
        products = products.filter(stock_quantity=0)
    if prescription == "required":
        products = products.filter(is_prescription=True)
    elif prescription == "not_required":
        products = products.filter(is_prescription=False)
    return products


@require_GET
def api_products(request):
    return JsonResponse([product_data(product) for product in _filtered_products(request)], safe=False)

@require_GET
def api_product_detail(request, slug):
    return JsonResponse(product_data(get_object_or_404(Product.objects.select_related("category"), slug=slug, is_active=True)))


@require_GET
def api_categories(request):
    return JsonResponse([category_data(item) for item in Category.objects.all()], safe=False)


@require_GET
def api_cart(request):
    if not request.user.is_authenticated:
        return _error("Authentication required.", 401)
    return JsonResponse(cart_data(_cart_for(request.user)))


@require_POST
def api_cart_add(request):
    if not request.user.is_authenticated:
        return _error("Authentication required.", 401)
    data = _body(request)
    if data is None:
        return _error("Invalid JSON body.")
    try:
        product_id = int(data.get("product_id", data.get("product", 0)))
        quantity = int(data.get("quantity", 1))
    except (TypeError, ValueError):
        return _error("Product and quantity must be whole numbers.")
    if quantity < 1:
        return _error("Quantity must be at least one.")
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    if product.stock_quantity < quantity:
        return _error("This quantity is not available in stock.", 409)
    cart = _cart_for(request.user)
    item, created = CartItem.objects.get_or_create(cart=cart, product=product, defaults={"quantity": quantity})
    if not created:
        if item.quantity + quantity > product.stock_quantity:
            return _error("This quantity is not available in stock.", 409)
        item.quantity += quantity
        item.save(update_fields=["quantity"])
    return JsonResponse(cart_data(cart), status=201)


@require_POST
def api_cart_remove(request):
    if not request.user.is_authenticated:
        return _error("Authentication required.", 401)
    data = _body(request)
    if data is None:
        return _error("Invalid JSON body.")
    try:
        item_id = int(data.get("item_id", 0))
    except (TypeError, ValueError):
        return _error("Cart item id must be a whole number.")
    _cart_for(request.user).items.filter(pk=item_id).delete()
    return JsonResponse(cart_data(_cart_for(request.user)))


@require_POST
def api_cart_update(request):
    if not request.user.is_authenticated:
        return _error("Authentication required.", 401)
    data = _body(request)
    if data is None:
        return _error("Invalid JSON body.")
    try:
        item_id, quantity = int(data.get("item_id", 0)), int(data.get("quantity", 0))
    except (TypeError, ValueError):
        return _error("Cart item and quantity must be whole numbers.")
    item = get_object_or_404(_cart_for(request.user).items.select_related("product"), pk=item_id)
    if quantity <= 0:
        item.delete()
    elif quantity > item.product.stock_quantity:
        return _error("This quantity is not available in stock.", 409)
    else:
        item.quantity = quantity
        item.save(update_fields=["quantity"])
    return JsonResponse(cart_data(_cart_for(request.user)))


@require_POST
@login_required
def api_checkout(request):
    cart = _cart_for(request.user)
    with transaction.atomic():
        items = list(cart.items.select_related("product").select_for_update())
        if not items:
            return _error("Your cart is empty.")
        delivery_method = request.POST.get("delivery_method", Order.DeliveryMethod.DELIVERY).strip().lower()
        if delivery_method not in Order.DeliveryMethod.values:
            return _error("Choose delivery or pick up.")
        for item in items:
            if item.quantity > item.product.stock_quantity:
                return _error(f"{item.product.name} no longer has enough stock.", 409)
        requires_prescription = any(item.product.is_prescription for item in items)
        prescription = request.FILES.get("prescription")
        if requires_prescription and not prescription:
            return _error("Upload a prescription for the prescription-required medicine(s).")
        if requires_prescription:
            upload_error = _prescription_error(prescription)
            if upload_error:
                return _error(upload_error)
        subtotal = sum(item.quantity * item.product.price for item in items)
        delivery_fee = DELIVERY_FEE if delivery_method == Order.DeliveryMethod.DELIVERY else 0
        order = Order.objects.create(
            user=request.user, delivery_method=delivery_method, total=subtotal + delivery_fee,
            prescription_file=prescription if requires_prescription else None,
        )
        Payment.objects.create(
            order=order,
            status=Payment.Status.SUCCEEDED,
            amount_total=order.total,
            amount_paid=order.total,
            paid_at=timezone.now(),
        )
        for item in items:
            OrderItem.objects.create(order=order, product=item.product, quantity=item.quantity, unit_price=item.product.price)
            item.product.stock_quantity -= item.quantity
            item.product.save(update_fields=["stock_quantity"])
        cart.items.all().delete()
    return JsonResponse(order_data(order), status=201)


def _catalog_context(request, cart_page=False, paginate=False):
    products = _filtered_products(request)
    search = request.GET.get("search", "").strip()
    chosen_category = request.GET.get("category", "").strip()
    selected_type = request.GET.get("type", "")
    availability = request.GET.get("availability", "")
    prescription = request.GET.get("prescription", "")

    def url_with(**updates):
        params = request.GET.copy()
        params.pop("page", None)
        for key, value in updates.items():
            if value:
                params[key] = value
            elif key in params:
                del params[key]
        query = params.urlencode()
        return f"?{query}" if query else "/shop/"

    categories = Category.objects.all()
    category_links = [{"name": "All Conditions", "url": url_with(category=""), "active": not chosen_category or chosen_category.lower() in {"all", "all-conditions"}}]
    category_links.extend({"name": c.name, "url": url_with(category=c.slug or c.name), "active": chosen_category.lower() in {c.name.lower(), (c.slug or "").lower()}} for c in categories)
    product_types = sorted({item.strength.rsplit(" - ", 1)[1] for item in Product.objects.filter(is_active=True) if " - " in item.strength})
    active_filters = []
    if search:
        active_filters.append({"label": f"Search: {search}", "url": url_with(search="")})
    if selected_type and selected_type.lower() != "all":
        active_filters.append({"label": f"Type: {selected_type}", "url": url_with(type="")})
    if availability:
        active_filters.append({"label": f"Availability: {availability.replace('_', ' ')}", "url": url_with(availability="")})
    if prescription:
        active_filters.append({"label": "Prescription: " + ("Required" if prescription == "required" else "Not required"), "url": url_with(prescription="")})
    if chosen_category and chosen_category.lower() not in {"all", "all-conditions"}:
        active_filters.append({"label": f"Category: {chosen_category}", "url": url_with(category="")})

    result_count = products.count()
    pagination = Paginator(products, 12).get_page(request.GET.get("page")) if paginate else None
    page_links = [{"number": n, "url": url_with(page=n), "current": n == pagination.number} for n in pagination.paginator.page_range] if pagination else []
    if pagination:
        products = pagination.object_list
    cart = Cart.objects.filter(user=request.user).first() if request.user.is_authenticated else None
    all_cart_items = list(cart.items.select_related("product", "product__category") if cart else []) if cart_page else []
    cart_categories = {item.product.category_id: item.product.category for item in all_cart_items}
    cart_categories = sorted(cart_categories.values(), key=lambda category: category.name.lower())
    selected_cart_category = request.GET.get("category", "").strip()
    items = all_cart_items
    if selected_cart_category:
        items = [item for item in all_cart_items if item.product.category.slug == selected_cart_category]
    subtotal = sum(item.quantity * item.product.price for item in all_cart_items)
    delivery_method = request.GET.get("delivery_method", Order.DeliveryMethod.DELIVERY).strip().lower()
    if delivery_method not in Order.DeliveryMethod.values:
        delivery_method = Order.DeliveryMethod.DELIVERY
    delivery = DELIVERY_FEE if all_cart_items and delivery_method == Order.DeliveryMethod.DELIVERY else 0
    cart_count = cart.items.count() if cart else 0
    return {
        "products": products, "categories": categories, "category_links": category_links,
        "product_types": product_types, "search": search, "chosen_category": chosen_category,
        "selected_type": selected_type, "availability": availability, "prescription": prescription,
        "active_filters": active_filters, "has_filters": bool(active_filters), "result_count": result_count,
        "pagination": pagination, "page_links": page_links,
        "previous_url": url_with(page=pagination.previous_page_number()) if pagination and pagination.has_previous() else "",
        "next_url": url_with(page=pagination.next_page_number()) if pagination and pagination.has_next() else "",
        "cart_count": cart_count, "has_cart_items": cart_count > 0, "cart_items": items, "subtotal": subtotal,
        "cart_categories": cart_categories, "selected_cart_category": selected_cart_category,
        "delivery_method": delivery_method, "delivery": delivery, "delivery_fee": DELIVERY_FEE, "total": subtotal + delivery,
        "requires_prescription": any(item.product.is_prescription for item in all_cart_items),
        "cart_page": cart_page,
    }

@ensure_csrf_cookie
def shop_page(request):
    return render(request, "shop/shop.html", _catalog_context(request, paginate=True))


@ensure_csrf_cookie
def product_page(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    context = _catalog_context(request)
    context["product"] = product
    return render(request, "shop/product.html", context)


@ensure_csrf_cookie
def cart_page(request):
    if not request.user.is_authenticated:
        return redirect(f"/login/?next=/cart/")
    context = _catalog_context(request, cart_page=True)
    return render(request, "shop/cart.html", context)
