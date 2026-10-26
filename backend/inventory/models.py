from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Medicine(models.Model):
    name = models.CharField(max_length=150)
    strength = models.CharField(max_length=80)
    dosage_form = models.CharField(max_length=80)
    selling_unit = models.CharField(max_length=80, default="unit")
    description = models.TextField(blank=True)
    category_name = models.CharField(max_length=80, blank=True)
    prescription_required = models.BooleanField(default=False)
    selling_price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    reorder_level = models.PositiveIntegerField(default=10)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "strength", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(selling_price__gt=0), name="medicine_price_positive"
            )
        ]

    def clean(self):
        for field in ("name", "strength", "dosage_form"):
            setattr(self, field, getattr(self, field).strip())
            if not getattr(self, field):
                raise ValidationError({field: "This field cannot be blank."})

    def __str__(self):
        return f"{self.name} {self.strength} ({self.dosage_form})"


class Batch(models.Model):
    medicine = models.ForeignKey(
        Medicine, on_delete=models.PROTECT, related_name="batches"
    )
    batch_number = models.CharField(max_length=80)
    supplier_name = models.CharField(max_length=150)
    received_date = models.DateField(default=timezone.localdate)
    expiry_date = models.DateField()
    quantity_available = models.PositiveIntegerField(default=0)
    purchase_price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))]
    )

    class Meta:
        ordering = ["expiry_date", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["medicine", "batch_number"], name="batch_medicine_number_unique"
            ),
            models.CheckConstraint(
                condition=Q(expiry_date__gt=F("received_date")),
                name="batch_expiry_after_receipt",
            ),
            models.CheckConstraint(
                condition=Q(purchase_price__gte=0), name="batch_price_nonnegative"
            ),
        ]

    def clean(self):
        self.batch_number = self.batch_number.strip()
        self.supplier_name = self.supplier_name.strip()
        errors = {}
        if not self.batch_number:
            errors["batch_number"] = "Enter a batch number."
        if not self.supplier_name:
            errors["supplier_name"] = "Enter a supplier name."
        if self.received_date and self.received_date > timezone.localdate():
            errors["received_date"] = "Receipt date cannot be in the future."
        if (
            self.received_date
            and self.expiry_date
            and self.expiry_date <= self.received_date
        ):
            errors["expiry_date"] = "Expiry must be after receipt."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.medicine} / {self.batch_number} / {self.quantity_available} available / expires {self.expiry_date}"
