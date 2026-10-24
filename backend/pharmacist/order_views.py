"""Pharmacist order, sale and dashboard screens."""

from uuid import uuid4
from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, OperationalError
from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from inventory.models import Batch, Medicine
from orders.models import Allocation, Order, Payment
from orders.services import (
    NEXT_STATUS,
    advance_order,
    complete_order,
    create_order,
    save_allocations,
)
from prescriptions.models import Prescription
from .order_forms import AllocationFormSet, PaymentForm, SaleForm, SaleLineFormSet
from .views import NAVIGATION, pharmacist_required


def context(title, active, **values):
    return {
        "page_title": title,
        "page_key": active,
        "active_nav": active,
        "navigation": NAVIGATION,
        "uses_database": True,
        **values,
    }


def rows(formset):
    return [
        f.cleaned_data
        for f in formset.forms
        if f.cleaned_data and not f.cleaned_data.get("DELETE")
    ]


def error_text(error):
    if isinstance(error, ValidationError):
        return " ".join(error.messages)
    return "The data changed or the database is busy. Reload and try again; no partial transaction was saved."


@never_cache
@pharmacist_required
@require_safe
def dashboard(request):
    today = timezone.localdate()
    stock_filter = Q(batches__expiry_date__gt=today)
    low_stock = (
        Medicine.objects.filter(is_active=True)
        .annotate(
            available=Sum(
                "batches__quantity_available", filter=stock_filter, default=0
            ),
        )
        .filter(available__lte=F("reorder_level"))
    )
    return render(
        request,
        "pharmacist/dashboard.html",
        context(
            "Dashboard",
            "dashboard",
            pending_prescriptions=Prescription.objects.filter(status="pending").count(),
            open_orders=Order.objects.filter(kind="online")
            .exclude(status="completed")
            .count(),
            sales_today=Order.objects.filter(
                status="completed", completed_at__date=today
            ).count(),
            revenue_today=Payment.objects.filter(recorded_at__date=today).aggregate(
                total=Sum("amount")
            )["total"]
            or 0,
            low_stock=low_stock[:10],
            recent_orders=Order.objects.select_related("customer")[:8],
        ),
    )


class OrderFilterForm(forms.Form):
    q = forms.CharField(
        max_length=100, required=False, label="Customer or order reference"
    )
    status = forms.ChoiceField(
        choices=[
            ("open", "Open orders"),
            ("all", "All statuses"),
            *Order.Status.choices,
        ]
    )
    kind = forms.ChoiceField(
        choices=[("online", "Online"), ("walk_in", "Walk-in"), ("all", "All orders")]
    )


@never_cache
@pharmacist_required
@require_safe
def order_queue(request):
    data = request.GET.copy()
    data.setdefault("status", "open")
    data.setdefault("kind", "online")
    form = OrderFilterForm(data)
    orders = Order.objects.select_related("customer")
    status_code = 200
    filters = {"q": "", "status": "open", "kind": "online"}
    if form.is_valid():
        filters = form.cleaned_data
        if filters["kind"] != "all":
            orders = orders.filter(kind=filters["kind"])
        if filters["status"] == "open":
            orders = orders.exclude(status="completed")
        elif filters["status"] != "all":
            orders = orders.filter(status=filters["status"])
        q = filters["q"]
        if q:
            match = Q(contact_name__icontains=q) | Q(customer__email__icontains=q)
            ref = q.upper().removeprefix("ORD-")
            if ref.isascii() and ref.isdigit() and 0 < int(ref) <= 9223372036854775807:
                match |= Q(pk=int(ref))
            orders = orders.filter(match)
    else:
        orders = orders.none()
        status_code = 400
    page = Paginator(orders.order_by("created_at", "pk"), 10).get_page(
        request.GET.get("page")
    )
    return render(
        request,
        "pharmacist/order_queue.html",
        context(
            "Orders",
            "orders",
            filter_form=form,
            page_obj=page,
            filter_query=urlencode(filters),
        ),
        status=status_code,
    )


@never_cache
@pharmacist_required
@require_http_methods(["GET", "POST"])
def sale_form(request):
    if request.method == "GET":
        token = str(uuid4())
        tokens = request.session.get("sale_tokens", [])[-19:]
        request.session["sale_tokens"] = tokens + [token]
        form = SaleForm(initial={"submission_key": token})
        formset = SaleLineFormSet(prefix="lines")
    else:
        form = SaleForm(request.POST)
        formset = SaleLineFormSet(request.POST, prefix="lines")
        valid = form.is_valid()
        valid_lines = formset.is_valid()
        if valid and str(
            form.cleaned_data["submission_key"]
        ) not in request.session.get("sale_tokens", []):
            form.add_error(None, "This sale form expired. Open a new sale form.")
            valid = False
        if valid and valid_lines:
            try:
                order = create_order(
                    user=request.user,
                    kind=Order.Kind.WALK_IN,
                    lines=rows(formset),
                    **form.cleaned_data
                )
            except (ValidationError, IntegrityError, OperationalError) as error:
                form.add_error(None, error_text(error))
            else:
                return redirect("pharmacist:order_record", pk=order.pk)
    return render(
        request,
        "pharmacist/sale_form.html",
        context("New walk-in sale", "sales", form=form, formset=formset),
        status=400 if request.method == "POST" else 200,
    )


@never_cache
@pharmacist_required
@require_http_methods(["GET", "POST"])
def order_record(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("customer", "prescription"), pk=pk
    )
    initial = list(
        Allocation.objects.filter(item__order=order).values("item", "batch", "quantity")
    )
    action = request.POST.get("action") if request.method == "POST" else None
    formset = AllocationFormSet(
        request.POST if action == "allocate" else None,
        prefix="allocations",
        initial=initial,
        form_kwargs={"order": order},
    )
    payment_form = PaymentForm(request.POST if action == "complete" else None)
    errors = []
    status_code = 200
    if request.method == "POST":
        try:
            if action == "allocate" and formset.is_valid():
                save_allocations(pk, rows(formset), request.user)
                messages.success(
                    request,
                    "Batch selections saved. Stock is checked again at completion.",
                )
            elif action == "advance":
                advance_order(pk, request.POST.get("target"), request.user)
                messages.success(request, "Order status updated.")
            elif action == "complete" and payment_form.is_valid():
                complete_order(pk, user=request.user, **payment_form.cleaned_data)
                return redirect("pharmacist:receipt", pk=pk)
            else:
                errors.append("Check the form fields and selected action.")
        except (ValidationError, IntegrityError, OperationalError) as error:
            errors.append(error_text(error))
        if not errors:
            return redirect("pharmacist:order_record", pk=pk)
        status_code = 400
        order.refresh_from_db()
    target = NEXT_STATUS.get(order.status) if order.kind == "online" else None
    return render(
        request,
        "pharmacist/order_record.html",
        context(
            str(order),
            "orders",
            order=order,
            formset=formset,
            payment_form=payment_form,
            errors=errors,
            next_status=target,
            next_label=dict(Order.Status.choices).get(target),
            can_complete=order.status != "completed"
            and (order.kind == "walk_in" or order.status == "ready"),
        ),
        status=status_code,
    )


@never_cache
@pharmacist_required
@require_safe
def receipt(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("payment", "processed_by"),
        pk=pk,
        status="completed",
    )
    return render(
        request, "pharmacist/receipt.html", context("Receipt", "sales", order=order)
    )
