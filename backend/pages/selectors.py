"""Home reads the same live catalogue images as Product and the cart."""
from shop.selectors import active_products


def homepage_products(limit):
    products = list(active_products().order_by("homepage_order", "medicine__name", "pk")[:limit])
    for product in products:
        product.homepage_image_url = product.image_url
    return products
