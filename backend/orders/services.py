"""Validated transactions for order creation, allocation and completion."""

from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from inventory.models import Batch, Medicine
from prescriptions.models import Prescription

from .models import (
    Allocation,
    Order,
    OrderItem,
    OrderStatusEvent,
    Payment,
    StockMovement,
)


NEXT_STATUS = {
    "pending": "confirmed",
    "confirmed": "preparing",
    "preparing": "ready",
}


# ---------------------------------------------------------------------------
# Access control, locking and prescription checks
# ---------------------------------------------------------------------------


def require_pharmacist(user):
    if not (
        user.is_authenticated
        and user.is_active
        and user.account_type == "staff"
        and user.groups.filter(name="Pharmacist").exists()
    ):
        raise PermissionDenied(
            "Only pharmacists may process orders."
        )


def lock_order(pk):
    """Obtain a write lock before reading an order for mutation."""
    # SQLite does not implement SELECT FOR UPDATE.
    # This write acquires its writer lock inside the calling transaction.
    changed = Order.objects.filter(pk=pk).update(
        revision=F("revision") + 1
    )

    if not changed:
        raise ValidationError("Order no longer exists.")

    return Order.objects.select_related(
        "prescription",
        "customer",
    ).get(pk=pk)


def validate_prescription(order):
    order.clean()

    # Check both the order snapshot and the current medicine requirement.
    required = order.items.filter(
        prescription_required=True
    ).exists()

    required = required or order.items.filter(
        medicine__prescription_required=True
    ).exists()

    if required and not order.prescription_id:
        raise ValidationError(
            "An approved customer prescription is required."
        )

    if order.prescription_id:
        prescription = order.prescription

        if prescription.status != Prescription.Status.APPROVED:
            raise ValidationError(
                "The linked prescription must be approved first."
            )

        if (
            not prescription.document
            or not prescription.document.storage.exists(
                prescription.document.name
            )
        ):
            raise ValidationError(
                "The prescription document is missing."
            )


# ---------------------------------------------------------------------------
# Order creation
# ---------------------------------------------------------------------------


@transaction.atomic
def create_order(
    *,
    user,
    kind,
    lines,
    customer=None,
    prescription=None,
    contact_name="",
    contact_phone="",
    pickup_time=None,
    submission_key=None,
):
    require_pharmacist(user)

    # Repeated submissions reuse the existing order.
    if submission_key:
        existing = Order.objects.filter(
            submission_key=submission_key
        ).first()

        if existing:
            if existing.processed_by_id != user.pk:
                raise PermissionDenied(
                    "This submission belongs to another pharmacist."
                )

            return existing

    order = Order(
        kind=kind,
        customer=customer,
        prescription=prescription,
        contact_name=contact_name.strip(),
        contact_phone=contact_phone.strip(),
        pickup_time=pickup_time,
        processed_by=user,
    )

    if submission_key:
        order.submission_key = submission_key

    order.full_clean()
    order.save()

    OrderStatusEvent.objects.create(
        order=order,
        status=order.status,
        recorded_by=user,
    )

    if not lines:
        raise ValidationError("Select at least one medicine.")

    seen = set()
    total = Decimal("0.00")

    for line in lines:
        medicine = Medicine.objects.get(
            pk=line["medicine"].pk
        )
        quantity = line["quantity"]

        if not medicine.is_active:
            raise ValidationError(
                "Archived medicines cannot be sold."
            )

        if medicine.pk in seen:
            raise ValidationError(
                "Use one row per medicine."
            )

        seen.add(medicine.pk)

        item = OrderItem(
            order=order,
            medicine=medicine,
            medicine_name=str(medicine),
            selling_unit=medicine.selling_unit,
            prescription_required=medicine.prescription_required,
            quantity=quantity,
            unit_price=medicine.selling_price,
        )

        item.full_clean()
        item.save()
        total += item.line_total

    order.total_amount = total
    order.full_clean()
    order.save(update_fields=["total_amount"])

    # Online orders may initially await prescription review.
    if kind == Order.Kind.WALK_IN:
        validate_prescription(order)

    return order


# ---------------------------------------------------------------------------
# Allocation validation
# ---------------------------------------------------------------------------


def allocation_rows(order, rows=None):
    items = {
        item.pk: item
        for item in order.items.select_related("medicine")
    }

    if not items:
        raise ValidationError(
            "An empty order cannot be processed."
        )

    if rows is None:
        rows = list(
            Allocation.objects.filter(
                item__order=order
            ).select_related("item", "batch")
        )

    totals = defaultdict(int)
    batches = defaultdict(int)
    seen = set()
    validated = []

    for row in rows:
        if isinstance(row, dict):
            item_id = row["item"].pk
            batch_id = row["batch"].pk
            quantity = row["quantity"]

        else:
            item_id = row.item_id
            batch_id = row.batch_id
            quantity = row.quantity

        item = items.get(item_id)

        batch = (
            Batch.objects.select_related("medicine")
            .filter(pk=batch_id)
            .first()
        )

        if (
            not item
            or not batch
            or batch.medicine_id != item.medicine_id
        ):
            raise ValidationError(
                "Select a batch containing the ordered medicine."
            )

        if (
            not item.medicine.is_active
            or batch.expiry_date <= timezone.localdate()
        ):
            raise ValidationError(
                "Archived medicines and batches expiring today "
                "or earlier cannot be dispensed."
            )

        if quantity <= 0 or (item_id, batch_id) in seen:
            raise ValidationError(
                "Use positive quantities and one row "
                "per item/batch pair."
            )

        seen.add((item_id, batch_id))
        totals[item_id] += quantity
        batches[batch_id] += quantity

        if batches[batch_id] > batch.quantity_available:
            raise ValidationError(
                f"Insufficient stock in batch {batch.batch_number}."
            )

        validated.append((item, batch, quantity))

    if any(
        totals[item_pk] != item.quantity
        for item_pk, item in items.items()
    ):
        raise ValidationError(
            "Allocated quantities must exactly match "
            "every ordered quantity."
        )

    return validated


# ---------------------------------------------------------------------------
# Save batch selections
# ---------------------------------------------------------------------------


@transaction.atomic
def save_allocations(pk, rows, user):
    require_pharmacist(user)
    order = lock_order(pk)

    if order.status in (
        Order.Status.COMPLETED,
        Order.Status.CANCELLED,
    ):
        raise ValidationError(
            "Completed or cancelled orders cannot be changed."
        )

    validate_prescription(order)
    validated = allocation_rows(order, rows)

    Allocation.objects.filter(item__order=order).delete()

    for item, batch, quantity in validated:
        Allocation.objects.create(
            item=item,
            batch=batch,
            quantity=quantity,
        )

    return order


# ---------------------------------------------------------------------------
# Advance online orders
# ---------------------------------------------------------------------------


@transaction.atomic
def advance_order(pk, target, user):
    require_pharmacist(user)
    order = lock_order(pk)

    if (
        order.kind != Order.Kind.ONLINE
        or NEXT_STATUS.get(order.status) != target
    ):
        raise ValidationError(
            "Invalid or outdated order status transition."
        )

    validate_prescription(order)

    if not order.items.exists():
        raise ValidationError(
            "An empty order cannot be processed."
        )

    if target == Order.Status.READY:
        allocation_rows(order)

    order.status = target
    order.processed_by = user
    order.full_clean()
    order.save(update_fields=["status", "processed_by"])

    OrderStatusEvent.objects.create(
        order=order,
        status=order.status,
        recorded_by=user,
    )

    return order


# ---------------------------------------------------------------------------
# Payment, stock deduction and completion
# ---------------------------------------------------------------------------


@transaction.atomic
def complete_order(pk, method, cash_tendered, user):
    require_pharmacist(user)
    order = lock_order(pk)

    # Repeating a successful completion must not deduct stock again.
    if order.status == Order.Status.COMPLETED:
        return order

    if order.status == Order.Status.CANCELLED:
        raise ValidationError(
            "Cancelled orders cannot be completed."
        )

    if (
        order.kind == Order.Kind.ONLINE
        and order.status != Order.Status.READY
    ):
        raise ValidationError(
            "Online orders must be ready for pickup "
            "before completion."
        )

    validate_prescription(order)
    validated = allocation_rows(order)

    total = sum(
        (item.line_total for item in order.items.all()),
        Decimal("0.00"),
    )

    payment = Payment(
        order=order,
        method=method,
        amount=total,
        cash_tendered=(
            cash_tendered
            if method == Payment.Method.CASH
            else None
        ),
        recorded_by=user,
    )
    payment.full_clean()

    for item, batch, quantity in validated:
        changed = Batch.objects.filter(
            pk=batch.pk,
            quantity_available__gte=quantity,
            expiry_date__gt=timezone.localdate(),
            medicine__is_active=True,
        ).update(
            quantity_available=F("quantity_available") - quantity
        )

        if changed != 1:
            raise ValidationError(
                "Stock changed. Check the allocations and try again."
            )

        allocation = Allocation.objects.get(
            item=item,
            batch=batch,
        )

        StockMovement.objects.create(
            allocation=allocation,
            quantity=quantity,
            recorded_by=user,
        )

    payment.save()

    order.total_amount = total
    order.status = Order.Status.COMPLETED
    order.completed_at = timezone.now()
    order.processed_by = user
    order.full_clean()
    order.save(
        update_fields=[
            "total_amount",
            "status",
            "completed_at",
            "processed_by",
        ]
    )

    OrderStatusEvent.objects.create(
        order=order,
        status=order.status,
        recorded_by=user,
        recorded_at=order.completed_at,
    )

    return order


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


@transaction.atomic
def cancel_order(pk, reason, user):
    """Close an unfinished order without payment or stock deduction."""
    require_pharmacist(user)

    reason = (reason or "").strip()

    if not reason or len(reason) > 500:
        raise ValidationError(
            "Enter a cancellation reason of 1–500 characters."
        )

    order = lock_order(pk)

    if order.status in (
        Order.Status.COMPLETED,
        Order.Status.CANCELLED,
    ):
        raise ValidationError(
            "This order is already closed."
        )

    order.status = Order.Status.CANCELLED
    order.cancellation_reason = reason
    order.processed_by = user
    order.full_clean()
    order.save(
        update_fields=[
            "status",
            "cancellation_reason",
            "processed_by",
        ]
    )

    OrderStatusEvent.objects.create(
        order=order,
        status=order.status,
        recorded_by=user,
        note=reason,
    )

    return order