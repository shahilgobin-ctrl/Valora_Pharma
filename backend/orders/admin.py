from django.contrib import admin
from .models import Allocation, Order, OrderItem, Payment, StockMovement


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(ReadOnlyAdmin):
    list_display = ("id", "kind", "status", "customer", "total_amount", "created_at")
    list_filter = ("kind", "status")
    search_fields = ("customer__email", "contact_name")


for model in (OrderItem, Allocation, Payment, StockMovement):
    admin.site.register(model, ReadOnlyAdmin)
