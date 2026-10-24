from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Order(models.Model):
    class Kind(models.TextChoices):
        ONLINE = "online", "Online"
        WALK_IN = "walk_in", "Walk-in"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        PREPARING = "preparing", "Preparing"
        READY = "ready", "Ready for pickup"
        COMPLETED = "completed", "Completed"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    prescription = models.OneToOneField(
        "prescriptions.Prescription",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="order",
    )
    contact_name = models.CharField(max_length=150, blank=True)
    contact_phone = models.CharField(
        max_length=16,
        blank=True,
        validators=[
            RegexValidator(r"^\+?[0-9]{7,15}$", "Enter 7–15 digits with an optional +.")
        ],
    )
    pickup_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True, editable=False)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="processed_orders",
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    submission_key = models.UUIDField(default=uuid4, unique=True, editable=False)
    revision = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(total_amount__gte=0), name="order_total_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(kind="walk_in") | Q(kind="online", customer__isnull=False),
                name="online_requires_customer",
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "pending",
                        "confirmed",
                        "preparing",
                        "ready",
                        "completed",
                    ]
                ),
                name="order_valid_status",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status="completed",
                        completed_at__isnull=False,
                        processed_by__isnull=False,
                    )
                    | (~Q(status="completed") & Q(completed_at__isnull=True))
                ),
                name="order_completion_metadata",
            ),
        ]

    def clean(self):
        errors = {}
        if self.customer_id and self.customer.account_type != "customer":
            errors["customer"] = "Select a customer account."
        if self.kind == self.Kind.ONLINE and not self.customer_id:
            errors["customer"] = "Online orders require a customer."
        if self.prescription_id and self.prescription.customer_id != self.customer_id:
            errors["prescription"] = "The prescription must belong to this customer."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"ORD-{self.pk}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="items")
    medicine = models.ForeignKey("inventory.Medicine", on_delete=models.PROTECT)
    medicine_name = models.CharField(max_length=320)
    prescription_required = models.BooleanField(default=False)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order", "medicine"], name="one_medicine_per_order"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="item_quantity_positive"
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gt=0), name="item_price_positive"
            ),
        ]

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.medicine_name} × {self.quantity}"


class Allocation(models.Model):
    item = models.ForeignKey(
        OrderItem, on_delete=models.PROTECT, related_name="allocations"
    )
    batch = models.ForeignKey("inventory.Batch", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item", "batch"], name="one_allocation_per_item_batch"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="allocation_quantity_positive"
            ),
        ]

    def clean(self):
        if (
            self.item_id
            and self.batch_id
            and self.item.medicine_id != self.batch.medicine_id
        ):
            raise ValidationError("The batch must contain the ordered medicine.")


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card (simulated)"

    order = models.OneToOneField(
        Order, on_delete=models.PROTECT, related_name="payment"
    )
    method = models.CharField(max_length=10, choices=Method.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    cash_tendered = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="payment_amount_positive"
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        method="cash",
                        cash_tendered__gte=F("amount"),
                        cash_tendered__isnull=False,
                    )
                    | Q(method="card", cash_tendered__isnull=True)
                ),
                name="payment_cash_valid",
            ),
        ]

    @property
    def change(self):
        return (
            self.cash_tendered - self.amount
            if self.cash_tendered is not None
            else Decimal("0.00")
        )


class StockMovement(models.Model):
    allocation = models.OneToOneField(
        Allocation, on_delete=models.PROTECT, related_name="movement"
    )
    quantity = models.PositiveIntegerField()
    recorded_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
