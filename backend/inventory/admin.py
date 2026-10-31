"""Administration for the medicine catalogue and inventory batches."""

from django.contrib import admin

from .models import Batch, Medicine


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "strength",
        "dosage_form",
        "selling_unit",
        "selling_price",
        "reorder_level",
        "prescription_required",
        "is_active",
    )
    search_fields = (
        "name",
        "strength",
        "category_name",
    )
    list_filter = (
        "is_active",
        "prescription_required",
        "dosage_form",
    )

    def has_delete_permission(self, request, obj=None):
        # Archive medicines instead of deleting their records.
        return False


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = (
        "batch_number",
        "medicine",
        "supplier_name",
        "quantity_available",
        "purchase_price",
        "received_date",
        "expiry_date",
    )
    list_select_related = ("medicine",)
    search_fields = (
        "batch_number",
        "medicine__name",
        "medicine__strength",
        "supplier_name",
    )
    list_filter = ("expiry_date",)
    ordering = ("expiry_date", "pk")

    def has_delete_permission(self, request, obj=None):
        # Preserve batches referenced by allocations and stock movements.
        return False