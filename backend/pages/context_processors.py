"""Lazy shared header data; pages without the header do not query the cart."""
from django.utils.functional import SimpleLazyObject
from shop.selectors import cart_quantity


def public_header(request):
    return {"public_cart_count": SimpleLazyObject(lambda: cart_quantity(request.user))}
