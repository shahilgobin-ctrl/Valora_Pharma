"""Homepage presentation layered over the read-only shared catalogue."""
from shop.images import catalogue_image_url
from shop.selectors import active_products

from .models import HomepageProductImage


def homepage_products(limit):
    products = list(active_products().select_related("homepage_image_override")
                    .order_by("homepage_order", "medicine__name", "pk")[:limit])
    for product in products:
        try:
            image = product.homepage_image_override.image
        except HomepageProductImage.DoesNotExist:
            image = product.image
        product.homepage_image_url = catalogue_image_url(image) if image else product.image_url
    return products
