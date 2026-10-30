"""Database-backed inventory and reporting reads."""
from datetime import timedelta
from decimal import Decimal

from django.db.models import DateField, DurationField, ExpressionWrapper, IntegerField, F, Q, Sum, Value
from django.db.models.functions import Cast
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from shop.models import Payment
from .models import Batch, BatchHistory, InventoryPolicy, PurchaseOrder


def policy():
    return InventoryPolicy.objects.get(pk=1)


def medicines():
    from shop.inventory import products_with_availability
    return products_with_availability().select_related("category", "manager_details").annotate(
        reorder=Coalesce(F("manager_details__reorder_level"), Value(0)),
    ).order_by("name", "pk")


def batches_with_policy():
    return Batch.objects.select_related("product", "product__manager_details", "supplier").annotate(
        warning_days=Coalesce(F("product__manager_details__expiry_warning_days"), Value(policy().expiry_warning_days)),
    ).annotate(warning_until=Cast(Value(timezone.localdate()) + ExpressionWrapper(Cast(F("warning_days"), IntegerField()) * timedelta(days=1), output_field=DurationField()), DateField()))


def risks():
    active = medicines().filter(is_active=True)
    today = timezone.localdate()
    batches = batches_with_policy().filter(quantity__gt=0, is_archived=False)
    return {
        "out": active.filter(available=0),
        "low": active.filter(available__gt=0, available__lt=F("reorder")),
        "expiring": batches.filter(expiry_date__gte=today, expiry_date__lte=F("warning_until")),
        "expired": batches.filter(expiry_date__lt=today),
        "in_stock": active.filter(available__gt=0, available__gte=F("reorder")),
    }


def purchase_orders():
    return PurchaseOrder.objects.select_related("supplier", "created_by").prefetch_related("lines__product").order_by("-created_at", "-pk")


def paid_sales():
    return Payment.objects.filter(status=Payment.Status.SUCCEEDED)


def monthly_sales():
    today = timezone.localdate()
    first = today.replace(day=1)
    months = []
    for offset in range(5, -1, -1):
        absolute = first.year * 12 + first.month - 1 - offset
        months.append(first.replace(year=absolute // 12, month=absolute % 12 + 1))
    rows = paid_sales().filter(paid_at__date__gte=months[0], paid_at__date__lte=today).annotate(
        month=TruncMonth("paid_at")).values("month").annotate(total=Sum("amount_paid"))
    amounts = {(row["month"].year, row["month"].month): row["total"] for row in rows if row["month"]}
    maximum = max(amounts.values(), default=0)
    return [{"label": date.strftime("%b %Y"), "total": amounts.get((date.year, date.month), 0),
             "height": round(amounts.get((date.year, date.month), 0) / maximum * 100, 2) if maximum else 0}
            for date in months]


def supplier_events():
    """Supply receipts and metadata changes, without repeating sales/quantity-only events."""
    return BatchHistory.objects.select_related("batch", "actor").filter(
        Q(before={}) | Q(action__startswith="Receipt ")
        | ~Q(before__supplier_id=F("after__supplier_id"))
        | ~Q(before__purchase_price=F("after__purchase_price"))
        | ~Q(before__received_date=F("after__received_date"))
        | ~Q(before__expiry_date=F("after__expiry_date"))
    )
