"""Resolve catalogue image values consistently without product-name mappings."""
from django.templatetags.static import static


def catalogue_image_url(value):
    if not value:
        return static("shop/products/medicine.svg")
    if value.startswith(("/", "https://", "http://")):
        return value
    return static(value)
