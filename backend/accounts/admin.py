from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from .models import User

class AdminUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email",)

class AdminUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()

        groups = cleaned_data.get("groups")
        account_type = cleaned_data.get("account_type")
        is_superuser = cleaned_data.get("is_superuser", False)

        if groups is None:
            return cleaned_data

        # Ignore groups that do not represent pharmacy roles.
        staff_role_names = {"Pharmacist", "Pharmacy Manager"}
        selected_roles = {
            group.name
            for group in groups
            if group.name in staff_role_names
        }

        if selected_roles and account_type != User.AccountType.STAFF:
            self.add_error(
                "groups",
                "Pharmacy staff roles can only be assigned to staff accounts.",
            )

        # The ERD defines pharmacist and manager roles as mutually exclusive.
        if len(selected_roles) > 1:
            self.add_error(
                "groups",
                "Select either Pharmacist or Pharmacy Manager, not both.",
            )

        if is_superuser and account_type != User.AccountType.STAFF:
            self.add_error(
                "account_type",
                "A super administrator must have a staff account.",
            )

        # Super administrators receive permissions through is_superuser.
        if is_superuser and selected_roles:
            self.add_error(
                "groups",
                "Super administrators do not need a pharmacy staff role.",
            )

        return cleaned_data

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
