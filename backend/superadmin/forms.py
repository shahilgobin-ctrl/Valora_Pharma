import re
from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.models import Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone
from accounts.models import User, canonical_email
from accounts.access import user_has_role
from .models import Role, SystemSettings

def assignable_permissions():
    return Permission.objects.filter(content_type__app_label="superadmin", content_type__model="role").order_by("id")

class AdminLoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "username", "placeholder": "you@valora.mu"}))
    password = forms.CharField(strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    def __init__(self, *args, request=None, blocked=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.request, self.blocked, self.user = request, blocked, None

    def clean(self):
        data = super().clean()
        if self.blocked:
            raise ValidationError("Too many sign-in attempts. Please try again in 15 minutes.")
        if data.get("email") and data.get("password"):
            user = authenticate(self.request, email=canonical_email(data["email"]), password=data["password"])
            if user is None or not user_has_role(user, User.AccountType.ADMIN):
                raise ValidationError("Unable to sign in with these administrator credentials.")
            self.user = user
        return data

class AccountForm(forms.ModelForm):
    role = forms.ModelChoiceField(queryset=Role.objects.select_related("group").order_by("pk"), empty_label="Choose a role")
    password = forms.CharField(required=False, strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}), help_text="Required for a new account. Leave blank when editing to keep the existing password.")
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "date_of_birth", "gender", "is_active"]
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def clean_email(self):
        email = canonical_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean_date_of_birth(self):
        value = self.cleaned_data.get("date_of_birth")
        if value and value > timezone.localdate():
            raise ValidationError("Date of birth cannot be in the future.")
        return value

    def clean_phone(self):
        value = re.sub(r"[\s().-]", "", self.cleaned_data.get("phone", ""))
        if value and not re.fullmatch(r"\+?[0-9]{7,15}", value):
            raise ValidationError("Enter 7-15 digits, with an optional leading +.")
        return value

    def clean(self):
        data = super().clean()
        password = data.get("password")
        if not self.instance.pk and not password:
            self.add_error("password", "Enter a password for this account.")
        if password:
            candidate = User(email=data.get("email", ""), first_name=data.get("first_name", ""), last_name=data.get("last_name", ""))
            try:
                validate_password(password, candidate)
            except ValidationError as exc:
                self.add_error("password", exc)
        return data

class RolePermissionsForm(forms.Form):
    permissions = forms.ModelMultipleChoiceField(queryset=assignable_permissions(), required=False, widget=forms.CheckboxSelectMultiple)

class SettingsForm(forms.ModelForm):
    class Meta:
        model = SystemSettings
        fields = ["portal_name", "support_email", "page_size", "customer_registration"]
        labels = {"customer_registration": "Allow customer registration", "page_size": "Rows per page"}
        help_texts = {"portal_name": "Displayed in the sidebar and page titles.", "support_email": "Displayed as a support link in the sidebar.", "page_size": "Applies to user lists and audit logs."}
