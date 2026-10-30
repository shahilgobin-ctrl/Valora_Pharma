"""Storefront metadata for inventory medicines; never creates or edits stock."""
from django.utils.text import slugify

from .models import Category, Product


def ensure_storefront(medicine):
    category_name = medicine.category_name or "Medicines"
    category, _ = Category.objects.get_or_create(
        name=category_name,
        defaults={"slug": f"{slugify(category_name)[:80]}-{medicine.pk}"},
    )
    return Product.objects.get_or_create(medicine=medicine, defaults={
        "name": medicine.name, "slug": f"{slugify(medicine.name)[:140]}-{medicine.pk}",
        "category": category, "price": 0, "stock_quantity": 0,
    })[0]
