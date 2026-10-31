"""Orders, item snapshots, batch allocations, payments and status history."""

from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


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
        CANCELLED = "cancelled", "Cancelled"

    delivery_method = models.CharField(max_length=10, choices=[("pickup", "Pick up"), ("delivery", "Delivery")], default="pickup")
    delivery_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                       validators=[MinValueValidator(Decimal("0.00"))])

    kind = models.CharField(
        max_length=10,
        choices=Kind.choices,
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
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
    contact_name = models.CharField(
        max_length=150,
        blank=True,
    )
    contact_phone = models.CharField(
        max_length=16,
        blank=True,
        validators=[
            RegexValidator(
                r"^\+?[0-9]{7,15}$",
                "Enter 7–15 digits with an optional +.",
            ),
        ],
    )
    cancellation_reason = models.CharField(
        max_length=500,
        blank=True,
    )
    pickup_time = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="processed_orders",
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    submission_key = models.UUIDField(
        default=uuid4,
        unique=True,
        editable=False,
    )
    revision = models.PositiveIntegerField(
        default=0,
        editable=False,
    )

    class Meta:
        ordering = ["-created_at", "-pk"]

        constraints = [
            models.CheckConstraint(
                condition=(
                    (
                        Q(status="cancelled")
                        & ~Q(cancellation_reason="")
                    )
                    | (
                        ~Q(status="cancelled")
                        & Q(cancellation_reason="")
                    )
                ),
                name="order_cancellation_reason_state",
            ),
            models.CheckConstraint(
                condition=Q(total_amount__gte=0),
                name="order_total_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(kind="walk_in")
                    | Q(kind="online", customer__isnull=False)
                ),
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
                        "cancelled",
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
                    | (
                        ~Q(status="completed")
                        & Q(completed_at__isnull=True)
                    )
                ),
                name="order_completion_metadata",
            ),
        ]

    def clean(self):
        errors = {}

        self.cancellation_reason = (
            self.cancellation_reason or ""
        ).strip()

        if (
            self.status == self.Status.CANCELLED
            and not self.cancellation_reason
        ):
            errors["cancellation_reason"] = (
                "A cancellation reason is required."
            )

        if (
            self.status != self.Status.CANCELLED
            and self.cancellation_reason
        ):
            errors["cancellation_reason"] = (
                "Only cancelled orders can have a cancellation reason."
            )

        if (
            self.customer_id
            and self.customer.account_type != "customer"
        ):
            errors["customer"] = "Select a customer account."

        if self.kind == self.Kind.ONLINE and not self.customer_id:
            errors["customer"] = "Online orders require a customer."

        if (
            self.prescription_id
            and self.prescription.customer_id != self.customer_id
        ):
            errors["prescription"] = (
                "The prescription must belong to this customer."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"ORD-{self.pk}"


# ---------------------------------------------------------------------------
# Order items
# ---------------------------------------------------------------------------


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="items",
    )
    medicine = models.ForeignKey(
        "inventory.Medicine",
        on_delete=models.PROTECT,
    )

    # Snapshots preserve the details used when the order was created.
    medicine_name = models.CharField(max_length=320)
    selling_unit = models.CharField(
        max_length=80,
        default="unit",
    )
    prescription_required = models.BooleanField(default=False)

    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)]
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.01")),
        ],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order", "medicine"],
                name="one_medicine_per_order",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="item_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gt=0),
                name="item_price_positive",
            ),
        ]

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.medicine_name} × {self.quantity}"


# ---------------------------------------------------------------------------
# Batch allocations
# ---------------------------------------------------------------------------


class Allocation(models.Model):
    item = models.ForeignKey(
        OrderItem,
        on_delete=models.PROTECT,
        related_name="allocations",
    )
    batch = models.ForeignKey(
        "inventory.Batch",
        on_delete=models.PROTECT,
    )
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)]
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item", "batch"],
                name="one_allocation_per_item_batch",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="allocation_quantity_positive",
            ),
        ]

    def clean(self):
        if (
            self.item_id
            and self.batch_id
            and self.item.medicine_id != self.batch.medicine_id
        ):
            raise ValidationError(
                "The batch must contain the ordered medicine."
            )


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


class Payment(models.Model):
    is_simulated_online = models.BooleanField(default=False)
    refunded_at = models.DateTimeField(null=True, blank=True)
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card (simulated)"

    order = models.OneToOneField(
        Order,
        on_delete=models.PROTECT,
        related_name="payment",
    )
    method = models.CharField(
        max_length=10,
        choices=Method.choices,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    cash_tendered = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="payment_amount_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        method="cash",
                        cash_tendered__gte=F("amount"),
                        cash_tendered__isnull=False,
                    )
                    | Q(
                        method="card",
                        cash_tendered__isnull=True,
                    )
                ),
                name="payment_cash_valid",
            ),
        ]

    @property
    def change(self):
        if self.cash_tendered is not None:
            return self.cash_tendered - self.amount

        return Decimal("0.00")


# ---------------------------------------------------------------------------
# Stock movements
# ---------------------------------------------------------------------------


class StockMovement(models.Model):
    allocation = models.OneToOneField(
        Allocation,
        on_delete=models.PROTECT,
        related_name="movement",
    )
    quantity = models.PositiveIntegerField()
    recorded_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )


# ---------------------------------------------------------------------------
# Order status history
# ---------------------------------------------------------------------------


class OrderStatusEvent(models.Model):
    """Record a transition or an explicitly labelled legacy snapshot."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="status_events",
    )
    status = models.CharField(
        max_length=12,
        choices=Order.Status.choices,
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    note = models.CharField(
        max_length=500,
        blank=True,
    )

    class Meta:
        ordering = ["recorded_at", "pk"]