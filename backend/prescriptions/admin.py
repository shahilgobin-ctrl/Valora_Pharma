from django.contrib import admin

from .models import Prescription


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer",
        "status",
        "uploaded_at",
        "reviewed_by",
        "reviewed_at",
    )
    list_filter = ("status",)
    search_fields = ("customer__email",)
    list_select_related = ("customer", "reviewed_by")
    fields = (
        "id",
        "customer",
        "status",
        "uploaded_at",
        "reviewed_by",
        "reviewed_at",
        "rejection_reason",
    )
    readonly_fields = fields

    # Reviews will go through the pharmacist workflow.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False