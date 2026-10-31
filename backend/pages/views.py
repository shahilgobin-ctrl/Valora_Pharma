from django.conf import settings
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_safe

from shop.models import ShopSettings
from shop.selectors import cart_quantity, categories_with_images

from .selectors import homepage_products


@require_safe
def about(request):
    """Display fixed company information without querying a database."""
    return render(request, "pages/about.html", {"active_page": "about"})


@ensure_csrf_cookie
@require_safe
def home(request):
    """Render the public homepage from the same catalogue used by the shop."""
    return render(request, "home.html", {
        "categories": categories_with_images(),
        "products": homepage_products(settings.HOMEPAGE_PRODUCT_LIMIT),
        "shop_settings": ShopSettings.objects.filter(pk=1).first(),
        "cart_count": cart_quantity(request.user),
    })
