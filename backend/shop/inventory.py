"""Shared inventory reads: exclude known expired stock, retain legacy unbatched units."""
from django.db.models import F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone
from .models import Product


def products_with_availability():
    from manager.models import Batch
    expired = Batch.objects.filter(product_id=OuterRef("pk"), expiry_date__lt=timezone.localdate()).values("product_id").annotate(n=Sum("quantity")).values("n")
    return Product.objects.annotate(available=Greatest(Value(0), F("stock_quantity") - Coalesce(Subquery(expired), Value(0))))


def available_stock(product):
    if hasattr(product, "available"):
        return product.available
    expired = product.manager_batches.filter(expiry_date__lt=timezone.localdate()).aggregate(n=Sum("quantity"))["n"] or 0
    return max(0, product.stock_quantity - expired)
