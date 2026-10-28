from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.core.exceptions import ValidationError
from .models import User

class AdminUserCreationForm(UserCreationForm):
    def clean_account_type(self):
        account_type = self.cleaned_data["account_type"]
        if account_type == User.AccountType.ADMIN:
            raise ValidationError("Create administrators with the createsuperuser command.")
        return account_type

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
    list_display = ("email", "username", "first_name", "last_name", "account_type", "is_active", "is_staff")
    list_filter = ("account_type", "is_active", "is_staff", "is_superuser")
    search_fields = ("email", "username", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal details", {"fields": ("username", "first_name", "last_name", "date_of_birth", "gender", "phone")}),
        ("Pharmacy account", {"fields": ("account_type", "is_active")}),
        ("Admin permissions", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2", "account_type")}),
    )

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def save_model(self, request, obj, form, change):
        if not change and obj.account_type in (User.AccountType.STAFF, User.AccountType.SUPPLIER):
            obj.is_active = False
            obj.is_staff = False
            obj.is_superuser = False
        super().save_model(request, obj, form, change)

admin.site.site_header = "Valora Pharmacy Administration"
admin.site.site_title = "Valora Admin"
