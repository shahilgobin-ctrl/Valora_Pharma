import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import Cart, CartItem, Category, Order, OrderItem, Product
from .serializers import cart_data, category_data, order_data, product_data


DELIVERY_FEE = 100


def _body(request):
    try:
        return json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def _cart_for(user):
    return Cart.objects.get_or_create(user=user)[0]


@require_GET
def api_products(request):
    products = Product.objects.filter(is_active=True).select_related("category")
    search = request.GET.get("search", "").strip()
    category = request.GET.get("category", "").strip()
    if search:
        products = products.filter(Q(name__icontains=search) | Q(description__icontains=search) | Q(strength__icontains=search) | Q(category__name__icontains=search))
    if category and category.lower() not in {"all", "all-conditions"}:
        products = products.filter(Q(category__slug__iexact=category) | Q(category__name__iexact=category))
    return JsonResponse([product_data(product) for product in products], safe=False)


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
        for item in items:
            if item.quantity > item.product.stock_quantity:
                return _error(f"{item.product.name} no longer has enough stock.", 409)
        subtotal = sum(item.quantity * item.product.price for item in items)
        order = Order.objects.create(user=request.user, total=subtotal + DELIVERY_FEE)
        for item in items:
            OrderItem.objects.create(order=order, product=item.product, quantity=item.quantity, unit_price=item.product.price)
            item.product.stock_quantity -= item.quantity
            item.product.save(update_fields=["stock_quantity"])
        cart.items.all().delete()
    return JsonResponse(order_data(order), status=201)


def _catalog_context(request, cart_page=False):
    products = Product.objects.filter(is_active=True).select_related("category")
    search = request.GET.get("search", "").strip()
    chosen_category = request.GET.get("category", "All Conditions")
    if search:
        products = products.filter(Q(name__icontains=search) | Q(description__icontains=search) | Q(strength__icontains=search))
    if chosen_category != "All Conditions":
        products = products.filter(category__name__iexact=chosen_category)
    cart = None
    if request.user.is_authenticated:
        cart = Cart.objects.filter(user=request.user).first()
    items = list(cart.items.select_related("product", "product__category") if cart else []) if cart_page else []
    subtotal = sum(item.quantity * item.product.price for item in items)
    return {"products": products, "categories": Category.objects.all(), "search": search,
            "chosen_category": chosen_category, "cart_count": cart.items.count() if cart else 0,
            "cart_items": items, "subtotal": subtotal, "delivery": DELIVERY_FEE if items else 0,
            "total": subtotal + (DELIVERY_FEE if items else 0), "cart_page": cart_page}


@ensure_csrf_cookie
def shop_page(request):
    return render(request, "shop/shop.html", _catalog_context(request))


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
