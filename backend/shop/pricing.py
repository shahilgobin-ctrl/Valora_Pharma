"""Shared pricing rules; monetary values come from database records."""
from django.core.exceptions import ImproperlyConfigured

from .models import ShopSettings


def cart_totals(subtotal, *, has_items):
    if not has_items:
        return {"subtotal": subtotal, "delivery": 0, "total": subtotal}
    try:
        delivery = ShopSettings.objects.values_list("delivery_fee", flat=True).get(pk=1)
    except ShopSettings.DoesNotExist as error:
        raise ImproperlyConfigured("Configure shop settings in Django admin before checkout.") from error
    return {"subtotal": subtotal, "delivery": delivery, "total": subtotal + delivery}
