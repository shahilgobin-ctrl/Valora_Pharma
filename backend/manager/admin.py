from django.contrib import admin
from .models import AuditEvent, Batch, BatchHistory, InventoryPolicy, MedicineDetails, PurchaseOrder, PurchaseOrderLine, StockMovement, Supplier


@admin.register(InventoryPolicy)
class PolicyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not InventoryPolicy.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockMovement)
class MovementAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "product", "batch", "delta", "actor", "reference")


@admin.register(AuditEvent)
class AuditAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "actor", "action", "description")


admin.site.register([Batch, BatchHistory, PurchaseOrder, PurchaseOrderLine], ReadOnlyAdmin)
admin.site.register([MedicineDetails, Supplier])
