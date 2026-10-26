"""Administration for the pharmacy's shared business details."""

from django.contrib import admin

from .models import PharmacyProfile


@admin.register(PharmacyProfile)
class PharmacyProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email")

    fields = (
        "name",
        "address",
        "phone",
        "email",
        "receipt_footer",
    )

    def has_add_permission(self, request):
        # The application uses one pharmacy profile.
        return (
            super().has_add_permission(request)
            and not PharmacyProfile.objects.exists()
        )

    def has_delete_permission(self, request, obj=None):
        return False