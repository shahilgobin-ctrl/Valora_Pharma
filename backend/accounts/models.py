import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


TERMS_VERSION = "2026-10-24"

def canonical_email(email):
    """Use one case-insensitive representation for all account operations."""
    return (email or "").strip().lower()

class UserManager(BaseUserManager):
    use_in_migrations = True

    def get_by_natural_key(self, email):
        return self.get(email=canonical_email(email))

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=canonical_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("account_type", "admin")
        if (extra_fields.get("is_staff") is not True
                or extra_fields.get("is_superuser") is not True
                or extra_fields.get("account_type") != "admin"):
            raise ValueError("A superuser must have staff, superuser, and admin-role privileges.")
        return self.create_user(email, password, **extra_fields)

class User(AbstractUser):
    class AccountType(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        STAFF = "staff", "Staff"
        SUPPLIER = "supplier", "Supplier"
        ADMIN = "admin", "Administrator"

    class Gender(models.TextChoices):
        FEMALE = "female", "Female"
        MALE = "male", "Male"
        OTHER = "other", "Other"
        PREFER_NOT_TO_SAY = "prefer_not_to_say", "Prefer not to say"

    # Existing accounts can remain without a username; new public customers choose one.
    username = models.CharField(max_length=30, null=True, blank=True)
    email = models.EmailField(unique=True)
    account_type = models.CharField(max_length=10, choices=AccountType.choices, default=AccountType.CUSTOMER)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, choices=Gender.choices, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    terms_version = models.CharField(max_length=20, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_case_insensitive_unique"),
            models.UniqueConstraint(Lower("username"), name="accounts_user_username_case_insensitive_unique"),
        ]

    def save(self, *args, **kwargs):
        self.email = canonical_email(self.email)
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class PasswordResetChallenge(models.Model):
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_challenges")
    account_type = models.CharField(max_length=10, choices=User.AccountType.choices)
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "created_at"], name="accounts_pr_user_created_idx")]


class EmailVerificationChallenge(models.Model):
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_verification_challenges")
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "created_at"], name="accounts_ev_user_created_idx")]
