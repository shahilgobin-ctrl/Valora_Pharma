from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


def prescription_upload_path(instance, filename):
    # Avoid storing customer-provided filenames.
    extension = Path(filename).suffix.lower()
    return f"prescriptions/{uuid4().hex}{extension}"


def validate_document_size(document):
    if document.size > 5 * 1024 * 1024:
        raise ValidationError("The prescription must not exceed 5 MB.")

    if document.size == 0:
        raise ValidationError("The prescription file cannot be empty.")


class Prescription(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="prescriptions",
        limit_choices_to={"account_type": "customer"},
    )
    document = models.FileField(
        upload_to=prescription_upload_path,
        validators=[
            FileExtensionValidator(allowed_extensions=["pdf", "jpg", "jpeg", "png"]),
            validate_document_size,
        ],
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    uploaded_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reviewed_prescriptions",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    rejection_reason = models.TextField(
        max_length=1000,
        blank=True,
        default="",
    )

    class Meta:
        ordering = ["-uploaded_at", "-pk"]
        indexes = [
            models.Index(
                fields=["status", "uploaded_at"],
                name="rx_status_uploaded_idx",
            ),
        ]
        constraints = [
            # Keep review information consistent with the status.
            models.CheckConstraint(
                condition=(
                    Q(
                        status="pending",
                        reviewed_by__isnull=True,
                        reviewed_at__isnull=True,
                        rejection_reason="",
                    )
                    | Q(
                        status="approved",
                        reviewed_by__isnull=False,
                        reviewed_at__isnull=False,
                        rejection_reason="",
                    )
                    | (
                        Q(
                            status="rejected",
                            reviewed_by__isnull=False,
                            reviewed_at__isnull=False,
                        )
                        & ~Q(rejection_reason="")
                    )
                ),
                name="rx_valid_review_state",
            ),
            models.CheckConstraint(
                condition=(
                    Q(reviewed_at__isnull=True) | Q(reviewed_at__gte=F("uploaded_at"))
                ),
                name="rx_review_after_upload",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        self.rejection_reason = (self.rejection_reason or "").strip()

        # Query safely even when an invalid foreign key was supplied.
        user_model = self._meta.get_field("customer").remote_field.model

        if self.customer_id:
            customer = user_model.objects.filter(pk=self.customer_id).first()

            if customer and customer.account_type != "customer":
                errors["customer"] = "The prescription must belong to a customer."

        if self.status == self.Status.PENDING:
            if self.reviewed_by_id:
                errors["reviewed_by"] = "A pending prescription cannot have a reviewer."
            if self.reviewed_at:
                errors["reviewed_at"] = (
                    "A pending prescription cannot have a review time."
                )
        elif self.status in (
            self.Status.APPROVED,
            self.Status.REJECTED,
        ):
            if not self.reviewed_by_id:
                errors["reviewed_by"] = "A reviewer is required."
            if not self.reviewed_at:
                errors["reviewed_at"] = "A review time is required."

        if self.status == self.Status.REJECTED:
            if not self.rejection_reason:
                errors["rejection_reason"] = (
                    "Enter a reason for rejecting this prescription."
                )
        elif self.rejection_reason:
            errors["rejection_reason"] = (
                "Only rejected prescriptions can have a rejection reason."
            )

        if self.uploaded_at and self.reviewed_at:
            if self.reviewed_at < self.uploaded_at:
                errors["reviewed_at"] = (
                    "The review time cannot precede the upload time."
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Prescription #{self.pk} — {self.get_status_display()}"
