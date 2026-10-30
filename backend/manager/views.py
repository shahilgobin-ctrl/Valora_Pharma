import csv
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import logout
from django.templatetags.static import static
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import DecimalField, F, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from shop.models import Category, Order, Payment, Product
from .access import manager_required
from .forms import (AdjustmentForm, BatchForm, CategoryForm, DateRangeForm, MedicineForm,
    ProductInventoryForm, BatchRemovalForm, PurchaseLines, PurchaseOrderForm, ReceiveLines, SupplierForm)
from .models import Batch, BatchHistory, MedicineDetails, PurchaseOrder, StockMovement, Supplier
from .selectors import medicines as catalogue, monthly_sales, paid_sales, policy, purchase_orders as orders_query, risks, batches_with_policy, supplier_events
from .services import adjust_stock, audit, receive_order, save_batch, remove_batch, delete_supplier


def page(request, template, active, **context):
    return render(request, f"manager/{template}.html", {"active": active, "local_preview": getattr(request, "manager_local_preview", False), **context})


def paginate(request, rows):
    return Paginator(rows, 25).get_page(request.GET.get("page"))


def error_text(error):
    return "; ".join(error.messages) if isinstance(error, ValidationError) else "The record changed or duplicates an existing record. Review and try again."


@manager_required
@require_GET
def dashboard(request):
    risk = risks()
    counts = {key: value.count() for key, value in risk.items()}
    stock_total = counts["out"] + counts["low"] + counts["in_stock"]
    sales = monthly_sales()
    specs = [
        ("Medicines", "medicines", "pill", "Manage the catalogue and medicine history"),
        ("Batches & expiry", "batches", "box", "Receive stock, review batches and set inventory rules"),
        ("Stock alerts", "alerts", "alert", "Review low stock and approaching expiry"),
        ("Suppliers", "suppliers", "user", "Manage supplier contacts and supply history"),
        ("Purchase orders", "orders", "doc", "Create orders and receive deliveries"),
        ("Customer orders", "customer_orders", "box", "Review orders, payments and sales reports"),
    ]
    shortcuts = [{"label": label, "url": reverse("manager:" + route), "icon": icon, "description": description}
                 for label, route, icon, description in specs]
    return page(request, "overview", "overview", total=catalogue().filter(is_active=True).count(),
        counts=counts, sales=sales, latest_sales=sales[-1], shortcuts=shortcuts, stock_total=stock_total,
        in_percent=counts["in_stock"] / stock_total * 100 if stock_total else 0,
        low_percent=(counts["in_stock"] + counts["low"]) / stock_total * 100 if stock_total else 0)


@manager_required
@require_GET
def medicines(request):
    rows = catalogue()
    q = request.GET.get("q", "").strip()
    if q:
        rows = rows.filter(Q(name__icontains=q) | Q(strength__icontains=q))
    category = request.GET.get("category", "")
    if category.isdigit():
        rows = rows.filter(category_id=category)
    status = request.GET.get("status", "active")
    if status in {"active", "archived"}:
        rows = rows.filter(is_active=status == "active")
    prescription = request.GET.get("prescription", "")
    if prescription in {"rx", "otc"}:
        rows = rows.filter(is_prescription=prescription == "rx")
    return page(request, "medicines", "medicines", rows=paginate(request, rows),
        categories=Category.objects.order_by("name"), q=q, status=status, selected_category=category, prescription=prescription)


@manager_required
@require_http_methods(["GET", "POST"])
def medicine_form(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk else Product()
    from_batch = not pk and request.GET.get("next") == "batch"
    form = MedicineForm(request.POST if request.method == "POST" else None, instance=product)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                creating = not product.pk
                product = form.save(commit=False)
                if creating:
                    product.image = static("shop/products/default-medicine.svg")
                product.save()
                MedicineDetails.objects.update_or_create(product=product, defaults={"dosage_form": form.cleaned_data["dosage_form"]})
                audit(request.user, "medicine_saved", f"{product.pk}: {product.name}")
            messages.success(request, "Medicine saved.")
            if from_batch:
                return redirect(reverse("manager:batch_new") + f"?product={product.pk}")
            return redirect("manager:medicine_detail", pk=product.pk)
        except IntegrityError as error:
            form.add_error(None, error_text(error))
    cancel = reverse("manager:batch_new") if from_batch else reverse("manager:medicine_detail", args=[pk]) if pk else reverse("manager:medicines")
    return page(request, "form", "batches" if from_batch else "medicines", form=form,
        title="Edit medicine" if pk else "Add medicine", cancel=cancel, medicine=product if pk else None)


@manager_required
@require_http_methods(["GET", "POST"])
def medicine_status(request, pk):
    product = get_object_or_404(Product, pk=pk)
    target = request.POST.get("target", "0" if product.is_active else "1")
    if request.method == "POST" and request.POST.get("confirmed") == "on" and target in {"0", "1"}:
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=pk)
            product.is_active = target == "1"
            product.save(update_fields=["is_active"])
            audit(request.user, "medicine_status", f"{product.pk}: active={product.is_active}")
        messages.success(request, "Medicine status updated; historical records preserved.")
        return redirect("manager:medicines")
    return page(request, "confirm", "medicines", title="Delete medicine" if target == "0" else "Restore medicine",
        description=product.name + (" will be removed from the active catalogue. Previous orders, batches and stock history will be retained." if target == "0" else " will be restored to the active catalogue."), target=target, cancel=reverse("manager:medicines"))


@manager_required
@require_http_methods(["GET", "POST"])
def batches(request):
    selected = request.GET.get("product", "")
    product = selected_record(Product, selected)
    inventory_form = None
    if product:
        details = MedicineDetails.objects.filter(product=product).first() or MedicineDetails(product=product)
        inventory_form = ProductInventoryForm(request.POST if request.method == "POST" else None, instance=details)
        if request.method == "POST" and inventory_form.is_valid():
            with transaction.atomic():
                details = inventory_form.save()
                audit(request.user, "inventory_rules_updated", f"{product.pk}: reorder={details.reorder_level}; expiry warning={details.expiry_warning_days}")
            messages.success(request, "Inventory settings saved for " + product.name + ".")
            return redirect(reverse("manager:batches") + f"?product={product.pk}")
    elif request.method == "POST":
        return HttpResponse("Select a medicine before changing inventory settings.", status=400)
    rows = filtered_batches(request)
    return page(request, "batches", "batches", rows=paginate(request, rows),
        q=request.GET.get("q", ""), suppliers=Supplier.objects.order_by("name"), products=Product.objects.order_by("name"),
        product=product, selected_supplier=request.GET.get("supplier", ""), state=request.GET.get("state", ""),
        stock=request.GET.get("stock", ""), show=request.GET.get("show", "active"), inventory_form=inventory_form)


@manager_required
@require_http_methods(["GET", "POST"])
def batch_form(request, pk=None):
    batch = get_object_or_404(Batch, pk=pk, is_archived=False) if pk else Batch()
    initial = {"product": request.GET.get("product"), "supplier": request.GET.get("supplier")} if not pk else {}
    form = BatchForm(request.POST if request.method == "POST" else None, instance=batch, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            saved = save_batch(form, request.user)
            messages.success(request, "Batch saved.")
            return redirect("manager:batch_detail", pk=saved.pk)
        except (ValidationError, IntegrityError) as error:
            form.add_error(None, error_text(error))
    return page(request, "form", "batches", form=form, title="Edit batch" if pk else "Add batch",
        cancel=reverse("manager:batch_detail", args=[pk]) if pk else reverse("manager:batches"), batch_record=batch if pk else None,
        batch_editor=True)


@manager_required
@require_GET
def alerts(request):
    risk = risks()
    return page(request, "alerts", "alerts", risk=risk, counts={key: value.count() for key, value in risk.items()},
        warning_days=policy().expiry_warning_days)


@manager_required
@require_http_methods(["GET", "POST"])
def adjustment(request):
    chosen = request.POST.get("batch", request.GET.get("batch", ""))
    batch = Batch.objects.filter(pk=int(chosen), is_archived=False).select_related("product").first() if chosen.isdigit() else None
    initial = {"batch": batch, "expected_quantity": batch.quantity} if batch else {}
    preview = request.method == "POST" and request.POST.get("_preview") == "1"
    data = request.POST.copy() if request.method == "POST" else None
    if preview:
        data["confirmed"] = "on"
    form = AdjustmentForm(data, initial=initial)
    if preview:
        if not form.is_valid():
            return JsonResponse({"error": "Check the quantity, reason and selected batch."}, status=400)
        chosen_batch = form.cleaned_data["batch"]
        after = chosen_batch.quantity + form.cleaned_data["delta"]
        if chosen_batch.quantity != form.cleaned_data["expected_quantity"] or after < 0:
            return JsonResponse({"error": "Stock changed or the resulting quantity would be negative. Reload the batch."}, status=409)
        return JsonResponse({"summary": f"{chosen_batch.product.name} / {chosen_batch.number}\nBatch quantity: {chosen_batch.quantity} → {after}\nReason: {form.cleaned_data['reason']}"})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            adjust_stock(data["batch"].pk, data["delta"], data["expected_quantity"], data["reason"], request.user)
            messages.success(request, "Stock adjusted and movement recorded.")
            return redirect("manager:movements")
        except (ValidationError, IntegrityError) as error:
            form.add_error(None, error_text(error))
    return page(request, "form", "batches", form=form, title="Adjust stock", cancel=reverse("manager:batch_detail", args=[batch.pk]) if batch else reverse("manager:batches"),
        description=f"Current batch quantity: {batch.quantity}" if batch else "Select a batch below, then load its current quantity.",
        adjustment=True, batch=batch, review=True)


@manager_required
@require_GET
def movements(request):
    rows = StockMovement.objects.select_related("product", "batch", "actor")
    for param, lookup in [("product", "product_id"), ("batch", "batch_id"), ("supplier", "batch__supplier_id")]:
        if request.GET.get(param):
            rows = rows.filter(**{lookup: int(request.GET[param]) if request.GET[param].isdigit() else 0})
    q = request.GET.get("q", "").strip()
    if q:
        rows = rows.filter(Q(product__name__icontains=q) | Q(batch__number__icontains=q) | Q(reference__icontains=q))
    date_form = DateRangeForm(request.GET)
    if date_form.is_valid():
        if date_form.cleaned_data.get("start"):
            rows = rows.filter(created_at__date__gte=date_form.cleaned_data["start"])
        if date_form.cleaned_data.get("end"):
            rows = rows.filter(created_at__date__lte=date_form.cleaned_data["end"])
    kind = request.GET.get("kind")
    if kind == "in":
        rows = rows.filter(delta__gt=0)
    elif kind == "out":
        rows = rows.filter(delta__lt=0)
    return page(request, "movements", "batches", rows=paginate(request, rows), q=q, date_form=date_form, selected_kind=kind)


@manager_required
@require_GET
def suppliers(request):
    q = request.GET.get("q", "").strip()
    rows = Supplier.objects.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(contact_name__icontains=q)).order_by("name")
    status = request.GET.get("status", "active")
    if status in {"active", "inactive"}:
        rows = rows.filter(is_active=status == "active")
    return page(request, "suppliers", "suppliers", rows=paginate(request, rows), q=q, status=status)


@manager_required
@require_http_methods(["GET", "POST"])
def supplier_form(request, pk=None):
    destination = request.GET.get("next", "")
    form = SupplierForm((request.POST if request.method == "POST" else None), instance=get_object_or_404(Supplier, pk=pk) if pk else None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            supplier = form.save()
            audit(request.user, "supplier_saved", supplier.name)
        messages.success(request, "Supplier saved.")
        if destination == "batch":
            product = request.GET.get("product", "")
            return redirect(reverse("manager:batch_new") + f"?supplier={supplier.pk}&product={product if product.isdigit() else ''}")
        if destination == "order":
            return redirect(reverse("manager:purchase_new") + f"?supplier={supplier.pk}")
        return redirect("manager:supplier_detail", pk=supplier.pk)
    return page(request, "form", "suppliers", form=form, title="Edit supplier" if pk else "Add supplier", cancel=reverse("manager:supplier_detail", args=[pk]) if pk else reverse("manager:suppliers"), supplier_record=form.instance if pk else None)


@manager_required
@require_http_methods(["GET", "POST"])
def categories(request):
    form = CategoryForm((request.POST if request.method == "POST" else None))
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                category = form.save()
                audit(request.user, "category_created", category.name)
            messages.success(request, "Category created.")
            return redirect("manager:categories")
        except IntegrityError as error:
            form.add_error(None, error_text(error))
    return page(request, "form", "medicines", title="Categories", form=form, cancel=reverse("manager:medicines"), category_rows=Category.objects.order_by("name"))


@manager_required
@require_GET
def settings_view(request):
    return redirect("manager:batches")


@manager_required
@require_GET
def purchase_orders(request):
    q = request.GET.get("q", "").strip()
    rows = orders_query()
    if request.GET.get("supplier", "").isdigit():
        rows = rows.filter(supplier_id=request.GET["supplier"])
    if q:
        rows = rows.filter(Q(supplier__name__icontains=q) | Q(notes__icontains=q) | Q(pk=int(q[3:]) if q.upper().startswith("PO-") and q[3:].isdigit() else int(q) if q.isdigit() else -1))
    dates = DateRangeForm(request.GET)
    if dates.is_valid():
        if dates.cleaned_data.get("start"):
            rows = rows.filter(ordered_date__gte=dates.cleaned_data["start"])
        if dates.cleaned_data.get("end"):
            rows = rows.filter(ordered_date__lte=dates.cleaned_data["end"])
    else:
        rows = rows.none()
    status = request.GET.get("status", "")
    if status in {"Pending", "Partial", "Received", "Cancelled"}:
        rows = [order for order in rows if order.status == status]
    return page(request, "purchase_orders", "orders", rows=paginate(request, rows), q=q, selected_status=status, date_form=dates)


@manager_required
@require_http_methods(["GET", "POST"])
def purchase_form(request):
    order = PurchaseOrder(created_by=request.user if request.user.is_authenticated else None)
    form = PurchaseOrderForm((request.POST if request.method == "POST" else None), instance=order, initial={"supplier": request.GET.get("supplier")})
    lines = PurchaseLines((request.POST if request.method == "POST" else None), instance=order)
    if request.method == "POST" and request.POST.get("_preview") == "1":
        valid_form, valid_lines = form.is_valid(), lines.is_valid()
        if not valid_form or not valid_lines:
            return JsonResponse({"error": "Complete the supplier, valid dates and positive medicine quantities/costs. Select each medicine once."}, status=400)
        summaries = []
        total = Decimal("0")
        for row in lines.cleaned_data:
            if not row or row.get("DELETE"):
                continue
            amount = row["quantity"] * row["unit_cost"]
            total += amount
            summaries.append(f"{row['product'].name} × {row['quantity']} @ Rs {row['unit_cost']:.2f} = Rs {amount:.2f}")
        return JsonResponse({"summary": f"Supplier: {form.cleaned_data['supplier'].name}\n" + "\n".join(summaries) + f"\nTotal: Rs {total:.2f}\nStock changes only when a delivery is received."})
    if request.method == "POST" and form.is_valid() and lines.is_valid():
        try:
            with transaction.atomic():
                order = form.save()
                lines.instance = order
                lines.save()
                audit(request.user, "purchase_created", order.reference)
            messages.success(request, "Purchase order created. Stock is unchanged until receipt.")
            return redirect("manager:purchase_detail", pk=order.pk)
        except IntegrityError as error:
            form.add_error(None, error_text(error))
    return page(request, "form", "orders", title="Create purchase order", form=form, formset=lines, cancel=reverse("manager:orders"), review=True)


@manager_required
@require_GET
def purchase_detail(request, pk):
    order = get_object_or_404(orders_query(), pk=pk)
    return page(request, "purchase_detail", "orders", order=order)


@manager_required
@require_http_methods(["GET", "POST"])
def receive(request, pk):
    order = get_object_or_404(orders_query(), pk=pk)
    lines = list(order.lines.all())
    initial = [{"line_id": line.pk, "expected_received": line.received_quantity, "medicine": line.product.name,
                "outstanding": line.outstanding} for line in lines]
    formset = ReceiveLines((request.POST if request.method == "POST" else None), initial=initial)
    error = ""
    if request.method == "POST" and request.POST.get("_preview") == "1":
        if not formset.is_valid():
            return JsonResponse({"error": "Complete valid delivery quantities, batch numbers and dates."}, status=400)
        by_id = {line.pk: line for line in lines}
        ids = [row["line_id"] for row in formset.cleaned_data]
        if len(ids) != len(set(ids)) or set(ids) != set(by_id) or order.cancelled:
            return JsonResponse({"error": "Invalid or cancelled order. Reload this page."}, status=409)
        summary = []
        for row in formset.cleaned_data:
            line = by_id[row["line_id"]]
            quantity = row["quantity"]
            if row["expected_received"] != line.received_quantity or quantity > line.outstanding:
                return JsonResponse({"error": "Stock changed or a quantity exceeds the amount outstanding."}, status=409)
            if quantity and row["received_date"] < order.ordered_date:
                return JsonResponse({"error": "A receipt cannot precede the purchase order."}, status=400)
            summary.append(f"{line.product.name}: receive {quantity}; remaining {line.outstanding - quantity}")
        if not any(row["quantity"] for row in formset.cleaned_data):
            return JsonResponse({"error": "Enter at least one quantity to receive."}, status=400)
        return JsonResponse({"summary": order.reference + "\n" + "\n".join(summary)})
    if request.method == "POST" and formset.is_valid():
        try:
            if request.POST.get("confirmed") != "on":
                raise ValidationError("Confirm the stock receipt before saving.")
            ids = [row["line_id"] for row in formset.cleaned_data]
            if len(ids) != len(set(ids)) or set(ids) != {line.pk for line in lines}:
                raise ValidationError("The order lines changed or are invalid. Reload this page.")
            receive_order(order.pk, formset.cleaned_data, request.user)
            messages.success(request, "Receipt recorded. Batch stock and purchase-order progress updated.")
            return redirect("manager:purchase_detail", pk=order.pk)
        except (ValidationError, IntegrityError) as exception:
            error = error_text(exception)
    return page(request, "receive", "orders", order=order, formset=formset, error=error)


@manager_required
@require_http_methods(["GET", "POST"])
def cancel_order(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk)
    error = ""
    if request.method == "POST" and request.POST.get("confirmed") == "on":
        with transaction.atomic():
            order = PurchaseOrder.objects.select_for_update().get(pk=pk)
            if order.lines.filter(received_quantity__gt=0).exists():
                error = "An order with received stock cannot be cancelled."
            else:
                order.cancelled = True
                order.save(update_fields=["cancelled"])
                audit(request.user, "purchase_cancelled", order.reference)
                return redirect("manager:purchase_detail", pk=pk)
    return page(request, "confirm", "orders", title="Cancel purchase order", description=order.reference,
        error=error, cancel=reverse("manager:purchase_detail", args=[pk]))


@manager_required
@require_GET
def customer_orders(request):
    rows = Order.objects.select_related("user", "payment").order_by("-created_at", "-pk")
    q = request.GET.get("q", "").strip()
    if q:
        rows = rows.filter(Q(user__email__icontains=q) | Q(pk=int(q) if q.isdigit() else -1))
    status = request.GET.get("status", "")
    if status in Order.Status.values:
        rows = rows.filter(status=status)
    dates = DateRangeForm(request.GET)
    if dates.is_valid():
        if dates.cleaned_data.get("start"):
            rows = rows.filter(created_at__date__gte=dates.cleaned_data["start"])
        if dates.cleaned_data.get("end"):
            rows = rows.filter(created_at__date__lte=dates.cleaned_data["end"])
    payment = request.GET.get("payment", "")
    if payment in {"pending", "succeeded", "failed"}:
        rows = rows.filter(payment__status=payment)
    return page(request, "customer_orders", "customer_orders", rows=paginate(request, rows), q=q, date_form=dates, selected_status=status, selected_payment=payment,
        status_choices=Order.Status.choices, payment_choices=Payment.Status.choices)


@manager_required
@require_GET
def customer_order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related("user", "payment").prefetch_related("items__product"), pk=pk)
    return page(request, "customer_order_detail", "customer_orders", order=order)


@manager_required
@require_GET
def reports(request):
    kind = request.GET.get("type", "sales")
    if kind not in {"sales", "inventory", "expiry", "purchasing", "history", "batch_history"}:
        kind = "sales"
    dates = DateRangeForm(request.GET)
    valid = dates.is_valid()
    product = selected_record(Product, request.GET.get("product", ""))
    batch = selected_record(Batch, request.GET.get("batch", ""))
    supplier = selected_record(Supplier, request.GET.get("supplier", ""))
    if kind == "sales":
        query, date_field, section = paid_sales().select_related("order__user").prefetch_related("order__items__product").order_by("-paid_at", "-pk"), "paid_at__date", "customer_orders"
        if product:
            query = query.filter(order__items__product=product).distinct()
    elif kind == "inventory":
        query, date_field, section = catalogue(), None, "medicines"
        if product:
            query = query.filter(pk=product.pk)
    elif kind == "expiry":
        query, date_field, section = filtered_batches(request), "expiry_date", "batches"
    elif kind == "purchasing":
        query, date_field, section = orders_query(), "ordered_date", "orders"
        if supplier:
            query = query.filter(supplier=supplier)
    elif kind == "history":
        query, date_field, section = StockMovement.objects.select_related("product", "batch", "actor"), "created_at__date", "batches"
        if product:
            query = query.filter(product=product)
        if batch:
            query = query.filter(batch=batch)
        if supplier:
            query = query.filter(batch__supplier=supplier)
    else:
        query, date_field, section = BatchHistory.objects.select_related("batch__product", "actor"), "created_at__date", "batches"
        if product:
            query = query.filter(batch__product=product)
        if batch:
            query = query.filter(batch=batch)
        if supplier:
            query = query.filter(Q(after__supplier_id=supplier.pk) | Q(before__supplier_id=supplier.pk))
    if valid and date_field:
        for name, lookup in [("start", "gte"), ("end", "lte")]:
            if dates.cleaned_data.get(name):
                query = query.filter(**{f"{date_field}__{lookup}": dates.cleaned_data[name]})
    if not valid:
        query = query.none()
    timestamp = lambda date: timezone.localtime(date).strftime("%Y-%m-%d %H:%M") if date else ""
    if kind == "sales":
        headers = ["Order", "Customer", "Items sold", "Medicine subtotal (Rs)", "Other charges (Rs)", "Paid at", "Amount paid (Rs)"]
        def row_data(payment):
            items = list(payment.order.items.all())
            subtotal = sum(item.quantity * item.unit_price for item in items)
            customer = payment.order.user
            name = (customer.first_name + " " + customer.last_name).strip() or customer.email
            description = "\n".join(f"{item.product.name} {item.product.strength} × {item.quantity} @ Rs {item.unit_price:.2f}" for item in items) or "No item details recorded"
            return [payment.order_id, name, description, subtotal if items else "Not recorded",
                max(0, payment.order.total - subtotal) if items else "Not recorded", timestamp(payment.paid_at), payment.amount_paid]
        total = query.aggregate(n=Sum("amount_paid"))["n"] or 0
        summary_label = "Total Rs"
    elif kind == "inventory":
        headers = ["Medicine", "Physical stock", "Available stock", "Reorder level", "Selling price (Rs)"]
        row_data = lambda item: [item.name, item.stock_quantity, item.available, item.reorder, item.price]
        total = query.aggregate(n=Sum("available"))["n"] or 0
        summary_label = "Available units"
    elif kind == "expiry":
        headers = ["Batch", "Medicine", "Supplier", "Quantity", "Purchase price (Rs)", "Received", "Expiry", "Status"]
        row_data = lambda item: [item.number, item.product.name, item.supplier.name, item.quantity, item.purchase_price,
                                 item.received_date, item.expiry_date, "Removed" if item.is_archived else item.expiry_status]
        total = query.aggregate(n=Sum("quantity"))["n"] or 0
        summary_label = "Units"
    elif kind == "purchasing":
        headers = ["Purchase order", "Supplier", "Order date", "Status", "Total (Rs)"]
        row_data = lambda item: [item.reference, item.supplier.name, item.ordered_date, item.status, item.total]
        total = query.aggregate(n=Sum(F("lines__quantity") * F("lines__unit_cost"), output_field=DecimalField(max_digits=18, decimal_places=2)))["n"] or Decimal("0")
        summary_label = "Total Rs"
    elif kind == "history":
        headers = ["Time", "Medicine", "Batch", "Change", "Previous stock", "New stock", "Reason", "Reference"]
        row_data = lambda item: [timestamp(item.created_at), item.product.name, item.batch.number if item.batch else "Unbatched",
                                 item.delta, item.previous_quantity, item.new_quantity, item.reason, item.reference]
        total, summary_label = query.count(), "Movements"
    else:
        headers = ["Time", "Batch", "Medicine", "Action", "Previous quantity", "New quantity", "Previous supplier", "Supplier", "Previous purchase price", "Purchase price (Rs)", "Previous received date", "Received", "Previous expiry", "Expiry"]
        row_data = lambda item: [timestamp(item.created_at), item.batch.number, item.after.get("medicine", ""), item.action,
            item.before.get("quantity", ""), item.after.get("quantity", ""), item.before.get("supplier", ""), item.after.get("supplier", ""),
            item.before.get("purchase_price", ""), item.after.get("purchase_price", ""), item.before.get("received_date", ""), item.after.get("received_date", ""), item.before.get("expiry_date", ""), item.after.get("expiry_date", "")]
        total, summary_label = query.count(), "Changes"
    if request.GET.get("format") == "csv" and valid:
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="manager-{kind}.csv"'
        writer = csv.writer(response)
        writer.writerow(headers)
        for item in query.iterator(chunk_size=200):
            writer.writerow(["'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else value for value in row_data(item)])
        return response
    if kind == "batch_history":
        headers = ["Date", "Batch", "Change", "Quantity", "Supplier / unit cost", "Received / expiry"]
        def row_data(item):
            before, after = item.before, item.after
            quantity = str(after.get("quantity", ""))
            if before and before.get("quantity") != after.get("quantity"):
                quantity = f"{before.get('quantity')} → {after.get('quantity')}"
            supplier_text = after.get("supplier", "")
            if before.get("supplier") and before.get("supplier") != after.get("supplier"):
                supplier_text = before["supplier"] + " → " + supplier_text
            price = "Rs " + after.get("purchase_price", "")
            if before.get("purchase_price") and before.get("purchase_price") != after.get("purchase_price"):
                price = "Rs " + before["purchase_price"] + " → " + price
            dates_text = "Received " + after.get("received_date", "") + "\nExpiry " + after.get("expiry_date", "")
            if before.get("expiry_date") and before.get("expiry_date") != after.get("expiry_date"):
                dates_text += "\nPrevious expiry " + before["expiry_date"]
            return [timestamp(item.created_at), item.batch.number, item.action, quantity, supplier_text + "\n" + price, dates_text]
    result = paginate(request, query)
    result.object_list = [row_data(item) for item in result.object_list]
    params = request.GET.copy()
    params["format"] = "csv"
    if product:
        section, back_url = "medicines", reverse("manager:medicine_detail", args=[product.pk])
    elif batch:
        section, back_url = "batches", reverse("manager:batch_detail", args=[batch.pk])
    elif supplier:
        section, back_url = "suppliers", reverse("manager:supplier_detail", args=[supplier.pk])
    else:
        back_url = reverse("manager:" + {"medicines": "medicines", "batches": "batches", "orders": "orders", "customer_orders": "customer_orders"}[section])
    requested_section = request.GET.get("section", "")
    section_routes = {"medicines": "medicines", "batches": "batches", "suppliers": "suppliers", "orders": "orders", "customer_orders": "customer_orders", "alerts": "alerts"}
    if requested_section in section_routes:
        section = requested_section
        if batch:
            back_url = reverse("manager:batch_detail", args=[batch.pk])
        elif section == "batches" and product:
            back_url = reverse("manager:batches") + f"?product={product.pk}"
        elif section == "medicines" and product:
            back_url = reverse("manager:medicine_detail", args=[product.pk])
        elif section == "suppliers" and supplier:
            back_url = reverse("manager:supplier_detail", args=[supplier.pk])
        else:
            back_url = reverse("manager:" + section_routes[section])
    return page(request, "reports", section, title=kind.replace("_", " ").title() + " report", kind=kind,
        date_form=dates, headers=headers, rows=result, total=total, count=result.paginator.count,
        summary_label=summary_label, export_url="?" + params.urlencode(), back_url=back_url,
        scope_name=product.name if product else batch.number if batch else supplier.name if supplier else "",
        scope_filters=[(key, value) for key, value in request.GET.items() if key not in {"type", "start", "end", "format", "page"}])




def selected_record(model, value):
    return get_object_or_404(model, pk=int(value) if value.isdigit() else 0) if value else None


def filtered_batches(request):
    rows = batches_with_policy()
    q = request.GET.get("q", "").strip()
    if q:
        rows = rows.filter(Q(number__icontains=q) | Q(product__name__icontains=q))
    for param, lookup in [("product", "product_id"), ("supplier", "supplier_id"), ("batch", "pk")]:
        value = request.GET.get(param, "")
        if value:
            rows = rows.filter(**{lookup: int(value) if value.isdigit() else 0})
    show = request.GET.get("show", "active")
    if show != "all":
        rows = rows.filter(is_archived=show == "removed")
    today = timezone.localdate()
    state = request.GET.get("state", "")
    if state == "expired":
        rows = rows.filter(expiry_date__lt=today)
    elif state == "expiring":
        rows = rows.filter(expiry_date__gte=today, expiry_date__lte=F("warning_until"))
    elif state == "ok":
        rows = rows.filter(expiry_date__gt=F("warning_until"))
    stock = request.GET.get("stock", "")
    if stock == "empty":
        rows = rows.filter(quantity=0)
    elif stock == "available":
        rows = rows.filter(quantity__gt=0)
    return rows


@manager_required
@require_GET
def medicine_detail(request, pk):
    product = get_object_or_404(catalogue(), pk=pk)
    tab = request.GET.get("tab", "batches")
    if tab not in {"batches", "history", "suppliers"}:
        tab = "batches"
    if tab == "history":
        rows = StockMovement.objects.filter(product=product).select_related("batch", "actor")
    elif tab == "suppliers":
        rows = supplier_events().filter(batch__product=product)
    else:
        rows = batches_with_policy().filter(product=product)
    legacy = batches_with_policy().filter(product=product, history__isnull=True)[:25] if tab == "suppliers" else []
    return page(request, "medicine_detail", "medicines", product=product, tab=tab, rows=paginate(request, rows), legacy_batches=legacy)


@manager_required
@require_GET
def batch_detail(request, pk):
    batch = get_object_or_404(batches_with_policy(), pk=pk)
    history = batch.history.select_related("actor")
    return page(request, "batch_detail", "batches", batch=batch, rows=paginate(request, history))


@manager_required
@require_http_methods(["GET", "POST"])
def batch_delete(request, pk):
    batch = get_object_or_404(Batch.objects.select_related("product", "supplier"), pk=pk, is_archived=False)
    form = BatchRemovalForm(request.POST if request.method == "POST" else None, initial={"expected_quantity": batch.quantity})
    if request.method == "POST" and form.is_valid():
        try:
            remove_batch(pk, form.cleaned_data["expected_quantity"], form.cleaned_data["reason"], request.user)
            messages.success(request, "Batch removed. Stock updated and history retained.")
            return redirect("manager:batches")
        except (ValidationError, IntegrityError) as error:
            form.add_error(None, error_text(error))
    return page(request, "form", "batches", form=form, title="Delete batch " + batch.number,
        description=f"This removes its {batch.quantity} remaining units from stock. The batch details and history will be retained.",
        cancel=reverse("manager:batch_detail", args=[pk]), destructive=True)


@manager_required
@require_http_methods(["GET", "POST"])
def supplier_delete(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == "POST" and request.POST.get("confirmed") == "on":
        messages.success(request, delete_supplier(pk, request.user))
        return redirect("manager:suppliers")
    used = supplier.batches.exists() or PurchaseOrder.objects.filter(supplier=supplier).exists() or BatchHistory.objects.filter(Q(before__supplier_id=pk) | Q(after__supplier_id=pk)).exists()
    return page(request, "confirm", "suppliers", title="Delete supplier", description=supplier.name +
        (" will be removed from active purchasing. Its linked batches and orders will be retained." if used else " will be deleted. It has no linked batches or purchase orders."),
        cancel=reverse("manager:supplier_detail", args=[pk]))


@manager_required
@require_GET
def supplier_detail(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    tab = request.GET.get("tab", "batches")
    if tab == "orders":
        rows = orders_query().filter(supplier=supplier)
    else:
        tab = "batches"
        rows = supplier_events().filter(Q(before__supplier_id=supplier.pk) | Q(after__supplier_id=supplier.pk))
    legacy = batches_with_policy().filter(supplier=supplier, history__isnull=True)[:25] if tab == "batches" else []
    return page(request, "supplier_detail", "suppliers", supplier=supplier, tab=tab, rows=paginate(request, rows), legacy_batches=legacy)


@require_POST
def signout(request):
    logout(request)
    return redirect("home")
