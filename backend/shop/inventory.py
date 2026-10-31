"""Shared inventory reads: exclude known expired stock, retain legacy unbatched units."""
from django.db.models import Case, F, IntegerField, OuterRef, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone
from .models import Product


def products_with_availability():
    from manager.models import Batch
    from inventory.models import Batch as PhysicalBatch
    from orders.models import Order, OrderItem
    expired = Batch.objects.filter(product_id=OuterRef("pk"), expiry_date__lt=timezone.localdate()).values("product_id").annotate(n=Sum("quantity")).values("n")
    physical = PhysicalBatch.objects.filter(medicine_id=OuterRef("medicine_id"),
        expiry_date__gt=timezone.localdate()).values("medicine_id").annotate(
        n=Sum("quantity_available")).values("n")
    reserved = OrderItem.objects.filter(medicine_id=OuterRef("medicine_id"),
        order__kind=Order.Kind.ONLINE).exclude(order__status__in=[
            Order.Status.COMPLETED, Order.Status.CANCELLED]).values("medicine_id").annotate(
        n=Sum("quantity")).values("n")
    return Product.objects.annotate(
        physical_stock=Case(When(medicine_id__isnull=False, then=Coalesce(Subquery(physical), Value(0))),
            default=F("stock_quantity"), output_field=IntegerField()),
        available=Greatest(Value(0), Case(
            When(medicine_id__isnull=False,
                 then=Coalesce(Subquery(physical), Value(0)) - Coalesce(Subquery(reserved), Value(0))),
            default=F("stock_quantity") - Coalesce(Subquery(expired), Value(0)),
            output_field=IntegerField())))


def available_stock(product):
    if product.medicine_id:
        return product.available_stock
    if hasattr(product, "available"):
        return product.available
    expired = product.manager_batches.filter(expiry_date__lt=timezone.localdate()).aggregate(n=Sum("quantity"))["n"] or 0
    return max(0, product.stock_quantity - expired)
