from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class InventoryPolicy(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    expiry_warning_days = models.PositiveSmallIntegerField(default=90)

    class Meta:
        permissions = [("access_manager", "Access Pharmacy Manager workspace")]
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="manager_single_policy")]

    def __str__(self):
        return "Inventory policy"


class MedicineDetails(models.Model):
    product = models.OneToOneField("shop.Product", on_delete=models.CASCADE, related_name="manager_details")
    dosage_form = models.CharField(max_length=80, blank=True)
    reorder_level = models.PositiveIntegerField(default=0)
    expiry_warning_days = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Days before expiry to show a warning for this medicine")


class Supplier(models.Model):
    name = models.CharField(max_length=180, unique=True)
    contact_name = models.CharField(max_length=160, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Batch(models.Model):
    # Manager metadata and history for the authoritative inventory batch.
    inventory_batch = models.OneToOneField("inventory.Batch", null=True, blank=True,
        on_delete=models.PROTECT, related_name="manager_record")
    product = models.ForeignKey("shop.Product", on_delete=models.PROTECT, related_name="manager_batches")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="batches")
    number = models.CharField(max_length=100)
    is_archived = models.BooleanField(default=False)
    quantity = models.PositiveIntegerField(default=0)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    received_date = models.DateField(default=timezone.localdate)
    expiry_date = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["product", "number"], name="manager_product_batch_unique")]
        ordering = ["expiry_date", "pk"]

    def clean(self):
        if self.expiry_date and self.received_date and self.expiry_date < self.received_date:
            raise ValidationError({"expiry_date": "Expiry cannot be before the received date."})
        if self.received_date and self.received_date > timezone.localdate():
            raise ValidationError({"received_date": "Received date cannot be in the future."})

    @property
    def expiry_status(self):
        today = timezone.localdate()
        if self.expiry_date < today:
            return "Expired"
        days = getattr(self, "warning_days", None)
        if days is None:
            detail = getattr(self.product, "manager_details", None)
            days = detail.expiry_warning_days if detail and detail.expiry_warning_days is not None else InventoryPolicy.objects.get(pk=1).expiry_warning_days
        return "Expiring" if self.expiry_date <= today + timedelta(days=days) else "OK"

    def __str__(self):
        return f"{self.number} / {self.product.name}"


class PurchaseOrder(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    ordered_date = models.DateField(default=timezone.localdate)
    expected_date = models.DateField()
    notes = models.TextField(blank=True)
    cancelled = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def reference(self):
        return f"PO-{self.pk:05d}"

    @property
    def total(self):
        return sum((line.quantity * line.unit_cost for line in self.lines.all()), Decimal("0"))

    @property
    def status(self):
        if self.cancelled:
            return "Cancelled"
        lines = list(self.lines.all())
        received = sum(line.received_quantity for line in lines)
        if lines and received == sum(line.quantity for line in lines):
            return "Received"
        return "Partial" if received else "Pending"

    def clean(self):
        if self.expected_date and self.ordered_date and self.expected_date < self.ordered_date:
            raise ValidationError({"expected_date": "Expected date cannot precede the order date."})


class PurchaseOrderLine(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("shop.Product", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    received_quantity = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(received_quantity__lte=models.F("quantity")), name="manager_no_over_receipt"),
            models.UniqueConstraint(fields=["order", "product"], name="manager_unique_po_product"),
        ]

    @property
    def outstanding(self):
        return self.quantity - self.received_quantity

    @property
    def line_total(self):
        return self.quantity * self.unit_cost


class StockMovement(models.Model):
    product = models.ForeignKey("shop.Product", on_delete=models.PROTECT)
    batch = models.ForeignKey(Batch, null=True, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="manager_stock_movements")
    delta = models.IntegerField()
    previous_quantity = models.PositiveIntegerField()
    new_quantity = models.PositiveIntegerField()
    reason = models.TextField()
    reference = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]


class BatchHistory(models.Model):
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="history")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
