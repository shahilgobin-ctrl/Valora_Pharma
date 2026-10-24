import re
from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import User, canonical_email

class RegistrationForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, label="First Name")
    last_name = forms.CharField(max_length=150, label="Last Name")
    date_of_birth = forms.DateField(
        label="Date Of Birth", input_formats=["%d-%m-%Y", "%Y-%m-%d"],
        widget=forms.DateInput(format="%d-%m-%Y"),
    )
    gender = forms.ChoiceField(
        choices=[("", "Select Gender"), *User.Gender.choices], label="Gender",
    )
    phone = forms.CharField(max_length=30, label="Phone Number")
    password = forms.CharField(
        strip=False, widget=forms.PasswordInput, label="Password",
        help_text="Use at least 8 characters. Avoid common or entirely numeric passwords.",
    )
    agree_terms = forms.BooleanField(
        required=True,
        label="I agree to the Terms and Conditions",
        error_messages={"required": "You must agree to the Terms and Conditions."},
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "date_of_birth", "gender", "email", "phone", "password"]

    def clean_email(self):
        email = canonical_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean_date_of_birth(self):
        date = self.cleaned_data["date_of_birth"]
        today = timezone.localdate()
        if date > today:
            raise ValidationError("Date of birth cannot be in the future.")
        if (today - date).days > 130 * 366:
            raise ValidationError("Enter a valid date of birth.")
        return date

    def clean_phone(self):
        phone = re.sub(r"[\s().-]", "", self.cleaned_data["phone"])
        if not re.fullmatch(r"\+?[0-9]{7,15}", phone):
            raise ValidationError("Enter 7–15 digits, with an optional leading +.")
        return phone

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        if password:
            candidate = User(
                email=cleaned.get("email", ""),
                first_name=cleaned.get("first_name", ""),
                last_name=cleaned.get("last_name", ""),
            )
            try:
                validate_password(password, candidate)
            except ValidationError as error:
                self.add_error("password", error)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user

class LoginForm(forms.Form):
    email = forms.EmailField(label="Email")
    password = forms.CharField(strip=False, widget=forms.PasswordInput, label="Password")

    def __init__(self, *args, request=None, account_type=User.AccountType.CUSTOMER, blocked=False, **kwargs):
        self.request = request
        self.account_type = account_type
        self.blocked = blocked
        self.user = None
        super().__init__(*args, **kwargs)

    def clean_email(self):
        return canonical_email(self.cleaned_data["email"])

    def clean(self):
        cleaned = super().clean()
        if self.blocked:
            raise ValidationError("Too many sign-in attempts. Please try again in 15 minutes.")
        if cleaned.get("email") and cleaned.get("password"):
            user = authenticate(
                self.request, email=cleaned["email"], password=cleaned["password"],
            )
            if user is None or user.account_type != self.account_type:
                raise ValidationError("Invalid email or password. Staff accounts must be approved before signing in.")
            self.user = user
        return cleaned


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(label="Email Address")

    def clean_email(self):
        return canonical_email(self.cleaned_data["email"])


class PasswordResetVerifyForm(forms.Form):
    code = forms.RegexField(
        regex=r"^\d{6}$", label="Verification Code",
        error_messages={"invalid": "Enter the six-digit code from your email."},
    )


class PasswordResetNewPasswordForm(forms.Form):
    new_password1 = forms.CharField(strip=False, widget=forms.PasswordInput, label="New Password")
    new_password2 = forms.CharField(strip=False, widget=forms.PasswordInput, label="Confirm New Password")

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("new_password1")
        password2 = cleaned.get("new_password2")
        if password1 and password2 and password1 != password2:
            self.add_error("new_password2", "The passwords do not match.")
        if password1:
            try:
                validate_password(password1, self.user)
            except ValidationError as error:
                self.add_error("new_password1", error)
        return cleaned
