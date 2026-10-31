"""Database reads shared by the public homepage and shop catalogue."""
from django.db.models import OuterRef, Subquery, Sum

from .models import CartItem, Category, Product


def active_products():
    return Product.objects.filter(medicine__isnull=False, medicine__is_active=True).select_related("category", "medicine").order_by("medicine__name", "pk")


def categories_with_images():
    image = Product.objects.filter(category_id=OuterRef("pk"), is_active=True).exclude(
        image=""
    ).order_by("pk").values("image")[:1]
    return Category.objects.annotate(card_image=Subquery(image)).order_by("display_order", "name", "pk")


def cart_quantity(user):
    if not user.is_authenticated:
        return 0
    return CartItem.objects.filter(cart__user=user).aggregate(total=Sum("quantity"))["total"] or 0
