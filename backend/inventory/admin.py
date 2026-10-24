from django.contrib import admin
from .models import Batch, Medicine


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "strength",
        "selling_price",
        "prescription_required",
        "is_active",
    )
    search_fields = ("name", "strength")
    list_filter = ("is_active", "prescription_required")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ("batch_number", "medicine", "quantity_available", "expiry_date")
    list_select_related = ("medicine",)
    search_fields = ("batch_number", "medicine__name")

    def has_delete_permission(self, request, obj=None):
        return False
