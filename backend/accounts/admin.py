from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from .models import User

class AdminUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email",)

class AdminUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"

@admin.register(User)
class PharmacyUserAdmin(UserAdmin):
    add_form = AdminUserCreationForm
    form = AdminUserChangeForm
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "account_type", "is_active", "is_staff")
    list_filter = ("account_type", "is_active", "is_staff", "is_superuser")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal details", {"fields": ("first_name", "last_name", "date_of_birth", "gender", "phone")}),
        ("Pharmacy account", {"fields": ("account_type", "is_active")}),
        ("Admin permissions", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2", "account_type", "is_active")}),
    )

admin.site.site_header = "Valora Pharmacy Administration"
admin.site.site_title = "Valora Admin"
