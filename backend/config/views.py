from django.db.models import Sum
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_safe

from manager.access import local_preview_allowed
from shop.inventory import products_with_availability
from shop.models import CartItem, Category


def start(request):
    return redirect("manager:dashboard" if local_preview_allowed(request) else "accounts:login")


@ensure_csrf_cookie
@require_safe
def public_home(request):
    active = products_with_availability().filter(is_active=True).order_by("homepage_order", "name", "pk")
    categories = list(Category.objects.order_by("display_order", "name"))
    default = static("shop/products/default-medicine.svg")

    def asset(path):
        return path if path.startswith(("/", "http://", "https://")) else static(path)

    for category in categories:
        category.card_image_url = asset(category.image) if category.image else default
    products = list(active[:4])
    for product in products:
        product.homepage_image_url = asset(product.image) if product.image else default
    count = 0
    if request.user.is_authenticated:
        count = CartItem.objects.filter(cart__user=request.user).aggregate(n=Sum("quantity"))["n"] or 0
    return render(request, "public_home.html", {
        "categories": categories, "products": products, "cart_count": count,
        "shop_settings": {"hero_image_url": static("home/photos/hero-pharmacy.jpg")},
    })
