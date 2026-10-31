"""Transactional writes and auditable inventory rules."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from shop.models import Product
from .models import AuditEvent, Batch, BatchHistory, PurchaseOrder, PurchaseOrderLine, StockMovement, Supplier


def sync_authoritative_batch(batch):
    """Write manager changes to the linked physical batch, never to shop stock."""
    if not batch.product.medicine_id:
        return
    from inventory.models import Batch as InventoryBatch
    from orders.models import Order, OrderItem

    medicine = batch.product.medicine
    existing = (InventoryBatch.objects.select_for_update().filter(pk=batch.inventory_batch_id).first()
                if batch.inventory_batch_id else
                InventoryBatch.objects.select_for_update().filter(
                    medicine=medicine, batch_number=batch.number).first())
    if existing and Batch.objects.exclude(pk=batch.pk).filter(inventory_batch=existing).exists():
        raise ValidationError("This physical batch is already managed by another record.")
    if not batch.is_archived and batch.expiry_date > timezone.localdate():
        other_stock = InventoryBatch.objects.filter(
            medicine=medicine, expiry_date__gt=timezone.localdate()).exclude(
            pk=existing.pk if existing else None).aggregate(n=Sum("quantity_available"))["n"] or 0
        pending = OrderItem.objects.filter(medicine=medicine, order__kind=Order.Kind.ONLINE).exclude(
            order__status__in=[Order.Status.COMPLETED, Order.Status.CANCELLED]).aggregate(
                n=Sum("quantity"))["n"] or 0
        if other_stock + batch.quantity < pending:
            raise ValidationError("This change would leave less usable stock than pending customer orders.")
    physical = existing or InventoryBatch(medicine=medicine)
    physical.batch_number = batch.number
    physical.supplier_name = batch.supplier.name
    physical.received_date = batch.received_date
    physical.expiry_date = batch.expiry_date
    physical.purchase_price = batch.purchase_price
    physical.quantity_available = batch.quantity
    physical.full_clean()
    physical.save()
    if batch.inventory_batch_id != physical.pk:
        Batch.objects.filter(pk=batch.pk).update(inventory_batch=physical)
        batch.inventory_batch_id = physical.pk


def recorded_actor(user):
    return user if user is not None and user.is_authenticated else None


def audit(user, action, description):
    AuditEvent.objects.create(actor=recorded_actor(user), action=action, description=description)


def _movement(product, batch, delta, actor, reason, reference=""):
    if product.medicine_id:
        from inventory.models import Batch as InventoryBatch
        previous = InventoryBatch.objects.filter(medicine_id=product.medicine_id).aggregate(
            n=Sum("quantity_available"))["n"] or 0
        if batch:
            sync_authoritative_batch(batch)
        current = InventoryBatch.objects.filter(medicine_id=product.medicine_id).aggregate(
            n=Sum("quantity_available"))["n"] or 0
        StockMovement.objects.create(product=product, batch=batch, actor=recorded_actor(actor),
            delta=current - previous, previous_quantity=previous, new_quantity=current,
            reason=reason, reference=reference)
        return
    previous = product.stock_quantity
    if previous + delta < 0:
        raise ValidationError("The resulting stock would be negative.")
    updated = Product.objects.filter(pk=product.pk, stock_quantity=previous).update(stock_quantity=F("stock_quantity") + delta)
    if updated != 1:
        raise ValidationError("Stock changed in another session. Reload and try again.")
    StockMovement.objects.create(product=product, batch=batch, actor=recorded_actor(actor), delta=delta,
        previous_quantity=previous, new_quantity=previous + delta, reason=reason, reference=reference)
    product.stock_quantity += delta


@transaction.atomic
def save_batch(form, actor):
    creating = not form.instance.pk
    if creating:
        batch = form.save(commit=False)
        product = Product.objects.select_for_update().get(pk=batch.product_id)
        opening = form.cleaned_data.get("stock_source") == "opening"
        if opening:
            if product.medicine_id:
                raise ValidationError("Linked medicines have no unbatched stock to allocate.")
            allocated = Batch.objects.filter(product=product).aggregate(n=Sum("quantity"))["n"] or 0
            if batch.quantity > max(0, product.stock_quantity - allocated):
                raise ValidationError("Allocation exceeds the existing unbatched stock. Use a new receipt for additional stock.")
        batch.save()
        record_batch(batch, actor, "Existing stock allocated" if opening else "Batch created")
        _movement(product, batch, 0 if opening else batch.quantity, actor,
                  "Existing stock allocated to batch" if opening else "Initial batch receipt")
    else:
        batch = Batch.objects.select_for_update().get(pk=form.instance.pk, is_archived=False)
        before = batch_snapshot(batch)
        if batch.quantity != form.cleaned_data["expected_quantity"]:
            raise ValidationError("This batch changed. Reload before editing.")
        product = Product.objects.select_for_update().get(pk=batch.product_id)
        delta = form.cleaned_data["quantity"] - batch.quantity
        if delta and not form.cleaned_data["reason"].strip():
            raise ValidationError("Give a reason when changing batch quantity.")
        for field in ("number", "supplier", "quantity", "purchase_price", "received_date", "expiry_date"):
            setattr(batch, field, form.cleaned_data[field])
        batch.full_clean()
        batch.save()
        record_batch(batch, actor, "Batch edited", before)
        if delta:
            _movement(product, batch, delta, actor, form.cleaned_data["reason"])
    audit(actor, "batch_saved", str(batch))
    return batch


@transaction.atomic
def adjust_stock(batch_id, delta, expected, reason, actor):
    batch = Batch.objects.select_for_update().get(pk=batch_id, is_archived=False)
    before = batch_snapshot(batch)
    if batch.quantity != expected:
        raise ValidationError("Batch stock changed. Reload and review the new quantity.")
    if not delta or not reason.strip():
        raise ValidationError("Provide a nonzero adjustment and a reason.")
    if batch.quantity + delta < 0:
        raise ValidationError("Adjustment would make batch stock negative.")
    product = Product.objects.select_for_update().get(pk=batch.product_id)
    changed = Batch.objects.filter(pk=batch.pk, quantity=expected).update(quantity=F("quantity") + delta)
    if changed != 1:
        raise ValidationError("Batch stock changed in another session.")
    _movement(product, batch, delta, actor, reason)
    batch.refresh_from_db()
    record_batch(batch, actor, "Stock adjustment: " + reason, before)
    audit(actor, "stock_adjusted", f"{batch.number}: {delta:+d}; {reason}")


@transaction.atomic
def receive_order(order_id, rows, actor):
    order = PurchaseOrder.objects.select_for_update().get(pk=order_id)
    if order.cancelled:
        raise ValidationError("A cancelled order cannot be received.")
    any_received = False
    for row in rows:
        quantity = row["quantity"]
        if quantity and row["received_date"] < order.ordered_date:
            raise ValidationError("Received date cannot precede the purchase order date.")
        if not quantity:
            continue
        line = PurchaseOrderLine.objects.select_for_update().get(pk=row["line_id"], order=order)
        if row.get("expected_received", line.received_quantity) != line.received_quantity:
            raise ValidationError("This receipt is stale or has already been submitted.")
        if quantity > line.outstanding:
            raise ValidationError("Received quantity exceeds the outstanding quantity.")
        product = Product.objects.select_for_update().get(pk=line.product_id)
        batch, created = Batch.objects.select_for_update().get_or_create(
            product=product, number=row["batch_number"], defaults={
                "supplier": order.supplier, "quantity": 0, "purchase_price": line.unit_cost,
                "received_date": row["received_date"], "expiry_date": row["expiry_date"],
            })
        before = {} if created else batch_snapshot(batch)
        if batch.is_archived:
            raise ValidationError("This batch was removed. Use a new batch number.")
        if not created and (batch.supplier_id != order.supplier_id or batch.expiry_date != row["expiry_date"] or batch.purchase_price != line.unit_cost):
            raise ValidationError("Existing batch metadata does not match this receipt.")
        batch.quantity += quantity
        batch.full_clean()
        batch.save()
        record_batch(batch, actor, "Receipt " + order.reference, before)
        changed = PurchaseOrderLine.objects.filter(pk=line.pk, received_quantity=line.received_quantity).update(
            received_quantity=F("received_quantity") + quantity)
        if changed != 1:
            raise ValidationError("Purchase order changed in another session. Reload it.")
        _movement(product, batch, quantity, actor, "Purchase order receipt", order.reference)
        any_received = True
    if not any_received:
        raise ValidationError("Enter at least one quantity to receive.")
    audit(actor, "purchase_received", order.reference)


def batch_snapshot(batch):
    return {"number": batch.number, "medicine": batch.product.name, "quantity": batch.quantity,
            "supplier_id": batch.supplier_id, "supplier": batch.supplier.name,
            "purchase_price": str(batch.purchase_price), "received_date": batch.received_date.isoformat(),
            "expiry_date": batch.expiry_date.isoformat(), "removed": batch.is_archived}


def record_batch(batch, actor, action, before=None):
    after = batch_snapshot(batch)
    if before == after:
        return
    BatchHistory.objects.create(batch=batch, actor=recorded_actor(actor), action=action,
                                before=before or {}, after=after)


@transaction.atomic
def remove_batch(batch_id, expected_quantity, reason, actor):
    batch = Batch.objects.select_for_update().select_related("product", "supplier").get(pk=batch_id)
    if batch.is_archived:
        raise ValidationError("This batch has already been removed.")
    if batch.quantity != expected_quantity:
        raise ValidationError("Batch quantity changed. Reload and review before removing it.")
    if not reason.strip():
        raise ValidationError("A reason is required.")
    before = batch_snapshot(batch)
    product = Product.objects.select_for_update().get(pk=batch.product_id)
    removed_quantity = batch.quantity
    batch.quantity = 0
    batch.is_archived = True
    batch.save(update_fields=["quantity", "is_archived"])
    _movement(product, batch, -removed_quantity, actor, "Batch removed: " + reason)
    record_batch(batch, actor, "Batch removed: " + reason, before)
    audit(actor, "batch_removed", f"{batch.pk}: {reason}")


@transaction.atomic
def delete_supplier(supplier_id, actor):
    supplier = Supplier.objects.select_for_update().get(pk=supplier_id)
    name = supplier.name
    # Referenced suppliers are removed from active purchasing, retaining traceability.
    if supplier.batches.exists() or PurchaseOrder.objects.filter(supplier=supplier).exists() or BatchHistory.objects.filter(Q(before__supplier_id=supplier.pk) | Q(after__supplier_id=supplier.pk)).exists():
        supplier.is_active = False
        supplier.save(update_fields=["is_active"])
        outcome = "Supplier removed from active purchasing; linked history retained."
    else:
        supplier.delete()
        outcome = "Supplier deleted."
    audit(actor, "supplier_removed", name)
    return outcome
