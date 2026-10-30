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
    ) + order.delivery_fee

    existing_payment = Payment.objects.filter(order=order).first()
    if existing_payment and (not existing_payment.is_simulated_online
                             or existing_payment.refunded_at or existing_payment.amount != total):
        raise ValidationError("The recorded payment does not match this order.")

    payment = existing_payment or Payment(
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

        # The physical inventory batch is authoritative. Keep manager's
        # linked reporting row current after this atomic pharmacist deduction.
        from manager.models import Batch as ManagerBatch
        ManagerBatch.objects.filter(inventory_batch_id=batch.pk).update(
            quantity=F("quantity") - quantity
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

    if not existing_payment:
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

    # This is a simulation only: preserve the payment record and record the
    # reversal rather than deleting it or collecting another payment.
    Payment.objects.filter(order=order, is_simulated_online=True, refunded_at__isnull=True).update(
        refunded_at=timezone.now())
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

@transaction.atomic
def checkout_walk_in(*, user, lines, method, cash_tendered, **details):
    """Create, allocate by earliest expiry, and complete one walk-in sale."""
    require_pharmacist(user)
    # create_order acquires SQLite's writer lock before stock is read.
    # An existing submission is returned without changing its original outcome.
    key = details.get("submission_key")
    existing = Order.objects.filter(submission_key=key).first() if key else None
    if existing:
        if existing.processed_by_id != user.pk:
            raise PermissionDenied("This submission belongs to another pharmacist.")
        return existing

    order = create_order(user=user, kind=Order.Kind.WALK_IN, lines=lines, **details)
    allocation_plan = []
    for item in order.items.select_related("medicine"):
        remaining = item.quantity
        batches = Batch.objects.select_for_update().filter(
            medicine=item.medicine,
            medicine__is_active=True,
            expiry_date__gt=timezone.localdate(),
            quantity_available__gt=0,
        ).order_by("expiry_date", "received_date", "pk")
        for batch in batches:
            quantity = min(remaining, batch.quantity_available)
            allocation_plan.append({"item": item, "batch": batch, "quantity": quantity})
            remaining -= quantity
            if remaining == 0:
                break
        if remaining:
            raise ValidationError(
                f"Insufficient usable stock for {item.medicine_name}. "
                "Review the cart and try again."
            )
    save_allocations(order.pk, allocation_plan, user)
    return complete_order(order.pk, method, cash_tendered, user)



@transaction.atomic
def checkout_online(*, user, prescription_upload=None, delivery_method="delivery"):
    """Place one paid simulated order in the pharmacist queue, without dispensing."""
    from django.db.models import Sum
    from accounts.access import user_has_role
    from shop.models import Cart, Product, ShopSettings
    if not user_has_role(user, "customer"):
        raise PermissionDenied("Only active customers may place orders.")
    if delivery_method not in {"pickup", "delivery"}:
        raise ValidationError("Choose delivery or pick up.")
    cart, _ = Cart.objects.get_or_create(user=user)
    # Serialize cart mutations and acquire SQLite's write lock before reading.
    Cart.objects.filter(pk=cart.pk).update(updated_at=timezone.now())
    items = list(cart.items.select_related("product__medicine").order_by("product__medicine_id"))
    if not items:
        raise ValidationError("Your cart is empty.")
    lines = []
    for item in items:
        if not item.product.medicine_id:
            raise ValidationError("This item must be linked to an inventory medicine.")
        medicine = Medicine.objects.select_for_update().get(pk=item.product.medicine_id)
        if not medicine.is_active or item.quantity < 1:
            raise ValidationError("This medicine is no longer available.")
        usable = Batch.objects.filter(medicine=medicine, expiry_date__gt=timezone.localdate()).aggregate(
            total=Sum("quantity_available"))["total"] or 0
        pending = OrderItem.objects.filter(medicine=medicine, order__kind="online").exclude(
            order__status__in=["completed", "cancelled"]).aggregate(total=Sum("quantity"))["total"] or 0
        if item.quantity > max(0, usable - pending):
            raise ValidationError(f"{medicine.name} no longer has enough available stock.")
        lines.append((medicine, item.quantity))
    requires_prescription = any(m.prescription_required for m, _ in lines)
    if requires_prescription and not prescription_upload:
        raise ValidationError("Upload a prescription for these medicines.")
    settings = ShopSettings.objects.get(pk=1)
    fee = Decimal(settings.delivery_fee) if delivery_method == "delivery" else Decimal("0")
    total = sum((m.selling_price * q for m, q in lines), Decimal("0")) + fee
    prescription = None
    try:
        if requires_prescription:
            prescription = Prescription(customer=user, document=prescription_upload)
            prescription.full_clean()
            prescription.save()
        order = Order(kind="online", customer=user, prescription=prescription,
                      contact_name=user.get_full_name()[:150], contact_phone=user.phone,
                      delivery_method=delivery_method, delivery_fee=fee, total_amount=total)
        order.full_clean()
        order.save()
        for medicine, quantity in lines:
            line = OrderItem(order=order, medicine=medicine, medicine_name=str(medicine),
                             selling_unit=medicine.selling_unit,
                             prescription_required=medicine.prescription_required,
                             quantity=quantity, unit_price=medicine.selling_price)
            line.full_clean()
            line.save()
        OrderStatusEvent.objects.create(order=order, status=order.status, recorded_by=user)
        payment = Payment(order=order, method="card", amount=total, recorded_by=user,
                          is_simulated_online=True)
        payment.full_clean()
        payment.save()
        cart.items.all().delete()
        return order
    except Exception:
        if prescription and prescription.document and prescription.pk:
            prescription.document.delete(save=False)
        raise
