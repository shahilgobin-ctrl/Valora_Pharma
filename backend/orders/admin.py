"""Read-only administration for orders and transaction records."""

from django.contrib import admin

from .models import (
    Allocation,
    Order,
    OrderItem,
    OrderStatusEvent,
    Payment,
    StockMovement,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Allow viewing records without bypassing workflow validation."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "kind",
        "status",
        "customer",
        "total_amount",
        "created_at",
    )
    list_filter = ("kind", "status")
    search_fields = (
        "customer__email",
        "contact_name",
        "contact_phone",
    )
    list_select_related = (
        "customer",
        "prescription",
        "processed_by",
    )


@admin.register(OrderItem)
class OrderItemAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "order",
        "medicine_name",
        "quantity",
        "selling_unit",
        "unit_price",
    )
    search_fields = ("medicine_name",)
    list_select_related = ("order", "medicine")


@admin.register(Allocation)
class AllocationAdmin(ReadOnlyAdmin):
    list_display = ("id", "item", "batch", "quantity")
    search_fields = (
        "item__medicine_name",
        "batch__batch_number",
    )
    list_select_related = (
        "item",
        "batch",
        "batch__medicine",
    )


@admin.register(Payment)
class PaymentAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "order",
        "method",
        "amount",
        "cash_tendered",
        "recorded_by",
        "recorded_at",
    )
    list_filter = ("method",)
    search_fields = ("recorded_by__email",)
    list_select_related = ("order", "recorded_by")


@admin.register(StockMovement)
class StockMovementAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "allocation",
        "quantity",
        "recorded_by",
        "recorded_at",
    )
    search_fields = (
        "allocation__batch__batch_number",
        "recorded_by__email",
    )
    list_select_related = ("allocation", "recorded_by")


@admin.register(OrderStatusEvent)
class OrderStatusEventAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "order",
        "status",
        "recorded_by",
        "recorded_at",
        "note",
    )
    list_filter = ("status",)
    search_fields = (
        "order__contact_name",
        "order__customer__email",
        "recorded_by__email",
        "note",
    )
    list_select_related = ("order", "recorded_by")
    ordering = ("-recorded_at", "-pk")