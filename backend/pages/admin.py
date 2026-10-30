from django.contrib import admin

from .models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("full_name", "subject", "email", "created_at")
    search_fields = ("full_name", "subject", "email")
    list_filter = ("created_at",)
    readonly_fields = ("full_name", "email", "phone", "subject", "message", "created_at")

    def has_add_permission(self, request):
        return False
