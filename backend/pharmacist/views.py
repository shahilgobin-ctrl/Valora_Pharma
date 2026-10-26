"""Pharmacist prescription, order, sale and inventory views."""

from functools import wraps
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, OperationalError
from django.db.models import F, Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_http_methods, require_safe

from accounts.models import User
from inventory.models import Medicine
from orders.models import Allocation, Order, Payment
from orders.services import (
    NEXT_STATUS,
    advance_order,
    cancel_order,
    complete_order,
    create_order,
    save_allocations,
)
from prescriptions.models import Prescription

from .forms import (
    AllocationFormSet,
    InventoryFilterForm,
    OrderFilterForm,
    PaymentForm,
    PrescriptionQueueFilterForm,
    PrescriptionReviewForm,
    SaleForm,
    SaleLineFormSet,
)


# ---------------------------------------------------------------------------
# Navigation and development preview configuration
# ---------------------------------------------------------------------------


NAVIGATION = [
    {
        "key": "dashboard",
        "route": "pharmacist:dashboard",
        "label": "Dashboard",
    },
    {
        "key": "prescriptions",
        "route": "pharmacist:prescription_queue",
        "label": "Prescriptions",
    },
    {
        "key": "orders",
        "route": "pharmacist:order_queue",
        "label": "Online orders",
    },
    {
        "key": "inventory",
        "route": "pharmacist:inventory",
        "label": "Inventory",
    },
    {
        "key": "sales",
        "route": "pharmacist:sale_form",
        "label": "New walk-in sale",
    },
]


# Retained for compatibility with the existing development preview routes.
PAGES = {
    "dashboard": ("Dashboard", "dashboard"),
    "prescription_queue": ("Prescription queue", "prescriptions"),
    "prescription_review": ("Prescription review", "prescriptions"),
    "order_queue": ("Online orders", "orders"),
    "order_detail": ("Order details", "orders"),
    "sale_form": ("New walk-in sale", "sales"),
    "sale_receipt": ("Sample receipt", "sales"),
}


# ---------------------------------------------------------------------------
# Access control and shared helpers
# ---------------------------------------------------------------------------


def pharmacist_required(view_func):
    """Require an active staff account in the Pharmacist group."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user

        # Pharmacy roles are separate from Django admin access.
        if (
            not user.is_active
            or user.account_type != User.AccountType.STAFF
            or not user.groups.filter(name="Pharmacist").exists()
        ):
            raise PermissionDenied(
                "Only pharmacists can access this page."
            )

        return view_func(request, *args, **kwargs)

    return login_required(
        wrapper,
        login_url="accounts:staff_login",
    )


def context(title, active, **values):
    """Build the shared context used by pharmacist workflow templates."""
    return {
        "page_title": title,
        "page_key": active,
        "active_nav": active,
        "navigation": NAVIGATION,
        "uses_database": True,
        **values,
    }


def rows(formset):
    """Return populated formset rows that are not marked for deletion."""
    return [
        form.cleaned_data
        for form in formset.forms
        if form.cleaned_data and not form.cleaned_data.get("DELETE")
    ]


def error_text(error):
    """Convert workflow errors into a message suitable for the form."""
    if isinstance(error, ValidationError):
        return " ".join(error.messages)

    return (
        "The data changed or the database is busy. "
        "Reload and try again; no partial transaction was saved."
    )


# ---------------------------------------------------------------------------
# Development previews
# ---------------------------------------------------------------------------


@pharmacist_required
@require_safe
def preview(request, page):
    """Display sample pages to authorised pharmacists during development."""
    if not settings.DEBUG or page not in PAGES:
        raise Http404("Preview unavailable.")

    title, active = PAGES[page]

    return render(
        request,
        f"pharmacist/{page}.html",
        {
            "page_title": title,
            "page_key": page,
            "active_nav": active,
            "navigation": NAVIGATION,
        },
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


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
                "batches__quantity_available",
                filter=stock_filter,
                default=0,
            )
        )
        .filter(available__lte=F("reorder_level"))
    )

    return render(
        request,
        "pharmacist/dashboard.html",
        context(
            "Dashboard",
            "dashboard",
            pending_prescriptions=Prescription.objects.filter(
                status=Prescription.Status.PENDING
            ).count(),
            open_orders=(
                Order.objects.filter(kind=Order.Kind.ONLINE)
                .exclude(
                    status__in=[
                        Order.Status.COMPLETED,
                        Order.Status.CANCELLED,
                    ]
                )
                .count()
            ),
            sales_today=Order.objects.filter(
                status=Order.Status.COMPLETED,
                completed_at__date=today,
            ).count(),
            revenue_today=(
                Payment.objects.filter(recorded_at__date=today)
                .aggregate(total=Sum("amount"))["total"]
                or 0
            ),
            low_stock=low_stock[:10],
            recent_orders=Order.objects.select_related("customer")[:8],
        ),
    )


# ---------------------------------------------------------------------------
# Prescription queue and review
# ---------------------------------------------------------------------------


@never_cache
@pharmacist_required
@require_safe
def prescription_queue(request):
    """Search and filter prescriptions with ten results per page."""
    filter_data = request.GET.copy()
    filter_data.setdefault("status", Prescription.Status.PENDING)
    filter_form = PrescriptionQueueFilterForm(filter_data)

    prescriptions = Prescription.objects.select_related("customer")
    selected_status = Prescription.Status.PENDING
    search_query = ""
    response_status = 200

    if filter_form.is_valid():
        selected_status = filter_form.cleaned_data["status"]
        search_query = filter_form.cleaned_data["q"]

        if selected_status != "all":
            prescriptions = prescriptions.filter(
                status=selected_status
            )

        if search_query:
            search_conditions = (
                Q(customer__first_name__icontains=search_query)
                | Q(customer__last_name__icontains=search_query)
                | Q(customer__email__icontains=search_query)
            )

            # Match searches containing both first and last names.
            name_parts = search_query.split()

            if len(name_parts) > 1:
                full_name_conditions = Q()

                for part in name_parts:
                    full_name_conditions &= (
                        Q(customer__first_name__icontains=part)
                        | Q(customer__last_name__icontains=part)
                    )

                search_conditions |= full_name_conditions

            reference = search_query.upper()

            if reference.startswith("RX-"):
                reference = reference[3:]

            # Bound numeric references to SQLite's signed integer range.
            if reference.isascii() and reference.isdigit():
                reference_id = int(reference)

                if 0 < reference_id <= 9223372036854775807:
                    search_conditions |= Q(pk=reference_id)

            prescriptions = prescriptions.filter(search_conditions)

    else:
        prescriptions = prescriptions.none()
        response_status = 400

    # Pending work is oldest first; reviewed history is newest first.
    if selected_status == Prescription.Status.PENDING:
        prescriptions = prescriptions.order_by("uploaded_at", "pk")
    else:
        prescriptions = prescriptions.order_by("-uploaded_at", "-pk")

    paginator = Paginator(prescriptions, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    filter_query = urlencode(
        {
            "q": search_query,
            "status": selected_status,
        }
    )

    return render(
        request,
        "pharmacist/prescription_queue.html",
        {
            "page_title": "Prescription queue",
            "page_key": "prescription_queue",
            "active_nav": "prescriptions",
            "navigation": NAVIGATION,
            "prescriptions": page_obj.object_list,
            "page_obj": page_obj,
            "filter_form": filter_form,
            "filter_query": filter_query,
            "selected_status": selected_status,
            "search_query": search_query,
            "uses_database": True,
        },
        status=response_status,
    )


@never_cache
@pharmacist_required
@require_http_methods(["GET", "POST"])
def prescription_detail(request, pk):
    """Display a prescription and record its first review decision."""
    prescription = get_object_or_404(
        Prescription.objects.select_related("customer", "reviewed_by"),
        pk=pk,
    )

    form = PrescriptionReviewForm(
        request.POST if request.method == "POST" else None
    )
    response_status = 200

    if request.method == "POST":
        if prescription.status != Prescription.Status.PENDING:
            form.add_error(
                None,
                "This prescription has already been reviewed.",
            )
            response_status = 409

        elif form.is_valid():
            decision = form.cleaned_data["decision"]

            if decision == Prescription.Status.APPROVED and (
                not prescription.document
                or not prescription.document.storage.exists(
                    prescription.document.name
                )
            ):
                form.add_error(
                    None,
                    "The document is missing. Approval is not possible.",
                )
                response_status = 400

            else:
                prescription.status = decision
                prescription.rejection_reason = form.cleaned_data[
                    "rejection_reason"
                ]
                prescription.reviewed_by = request.user
                prescription.reviewed_at = timezone.now()

                try:
                    # Reviewing a prescription does not modify its document.
                    prescription.full_clean(exclude=["document"])

                except ValidationError as error:
                    for message in error.messages:
                        form.add_error(None, message)

                    response_status = 400

                else:
                    # Only the first request can change a pending record.
                    updated = Prescription.objects.filter(
                        pk=prescription.pk,
                        status=Prescription.Status.PENDING,
                    ).update(
                        status=prescription.status,
                        rejection_reason=prescription.rejection_reason,
                        reviewed_by=request.user,
                        reviewed_at=prescription.reviewed_at,
                    )

                    if updated:
                        messages.success(
                            request,
                            f"Prescription RX-{prescription.pk} "
                            f"{prescription.get_status_display().lower()}.",
                        )

                        return redirect(
                            "pharmacist:prescription_detail",
                            pk=prescription.pk,
                        )

                    form.add_error(
                        None,
                        "Another pharmacist has already reviewed "
                        "this prescription. The latest decision is shown.",
                    )
                    response_status = 409

        else:
            response_status = 400

        # Display saved values after errors or a competing review.
        prescription.refresh_from_db()

    return render(
        request,
        "pharmacist/prescription_detail.html",
        {
            "page_title": f"Prescription RX-{prescription.pk}",
            "page_key": "prescription_detail",
            "active_nav": "prescriptions",
            "navigation": NAVIGATION,
            "prescription": prescription,
            "form": form,
            "uses_database": True,
            "document_extension": Path(
                prescription.document.name or ""
            ).suffix.lower(),
        },
        status=response_status,
    )


# ---------------------------------------------------------------------------
# Private prescription documents
# ---------------------------------------------------------------------------


@never_cache
@pharmacist_required
@require_safe
def prescription_document(request, pk):
    """Download a document only after checking pharmacist access."""
    prescription = get_object_or_404(Prescription, pk=pk)

    if not prescription.document:
        raise Http404("Prescription document unavailable.")

    extension = Path(prescription.document.name).suffix.lower()

    if extension not in {".pdf", ".jpg", ".jpeg", ".png"}:
        raise Http404("Unsupported document type.")

    try:
        document = prescription.document.open("rb")
    except FileNotFoundError:
        raise Http404("Prescription document unavailable.") from None

    response = FileResponse(
        document,
        as_attachment=True,
        filename=f"prescription-{prescription.pk}{extension}",
        content_type="application/octet-stream",
    )
    response["X-Content-Type-Options"] = "nosniff"

    return response


@never_cache
@pharmacist_required
@require_safe
@xframe_options_sameorigin
def prescription_document_preview(request, pk):
    """Display a private document to an authorised pharmacist."""
    prescription = get_object_or_404(Prescription, pk=pk)

    if not prescription.document:
        raise Http404("Document unavailable.")

    extension = Path(prescription.document.name).suffix.lower()

    content_types = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }

    content_type = content_types.get(extension)

    if content_type is None:
        raise Http404("Document format not supported.")

    try:
        document = prescription.document.open("rb")
    except FileNotFoundError:
        raise Http404("Document unavailable.") from None

    response = FileResponse(
        document,
        as_attachment=False,
        filename=f"prescription-{prescription.pk}{extension}",
        content_type=content_type,
    )

    # Allow embedding only within this application.
    response["Content-Security-Policy"] = "frame-ancestors 'self'"
    response["X-Content-Type-Options"] = "nosniff"

    return response


# ---------------------------------------------------------------------------
# Order queue
# ---------------------------------------------------------------------------


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

    filters = {
        "q": "",
        "status": "open",
        "kind": "online",
    }

    if form.is_valid():
        filters = form.cleaned_data

        if filters["kind"] != "all":
            orders = orders.filter(kind=filters["kind"])

        if filters["status"] == "open":
            orders = orders.exclude(
                status__in=[
                    Order.Status.COMPLETED,
                    Order.Status.CANCELLED,
                ]
            )
        elif filters["status"] != "all":
            orders = orders.filter(status=filters["status"])

        q = filters["q"]

        if q:
            match = (
                Q(contact_name__icontains=q)
                | Q(customer__email__icontains=q)
            )

            ref = q.upper().removeprefix("ORD-")

            if (
                ref.isascii()
                and ref.isdigit()
                and 0 < int(ref) <= 9223372036854775807
            ):
                match |= Q(pk=int(ref))

            orders = orders.filter(match)

    else:
        orders = orders.none()
        status_code = 400

    page = Paginator(
        orders.order_by("created_at", "pk"),
        10,
    ).get_page(request.GET.get("page"))

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


# ---------------------------------------------------------------------------
# Walk-in sale creation
# ---------------------------------------------------------------------------


@never_cache
@pharmacist_required
@require_http_methods(["GET", "POST"])
def sale_form(request):
    if request.method == "GET":
        token = str(uuid4())

        # Retain a limited number of tokens for open sale-form tabs.
        tokens = request.session.get("sale_tokens", [])[-19:]
        request.session["sale_tokens"] = tokens + [token]

        form = SaleForm(initial={"submission_key": token})
        formset = SaleLineFormSet(prefix="lines")

    else:
        form = SaleForm(request.POST)
        formset = SaleLineFormSet(
            request.POST,
            prefix="lines",
        )

        valid = form.is_valid()
        valid_lines = formset.is_valid()

        if valid and str(
            form.cleaned_data["submission_key"]
        ) not in request.session.get("sale_tokens", []):
            form.add_error(
                None,
                "This sale form expired. Open a new sale form.",
            )
            valid = False

        if valid and valid_lines:
            try:
                order = create_order(
                    user=request.user,
                    kind=Order.Kind.WALK_IN,
                    lines=rows(formset),
                    **form.cleaned_data,
                )

            except (
                ValidationError,
                IntegrityError,
                OperationalError,
            ) as error:
                form.add_error(None, error_text(error))

            else:
                return redirect(
                    "pharmacist:order_record",
                    pk=order.pk,
                )

    return render(
        request,
        "pharmacist/sale_form.html",
        context(
            "New walk-in sale",
            "sales",
            form=form,
            formset=formset,
        ),
        status=400 if request.method == "POST" else 200,
    )


# ---------------------------------------------------------------------------
# Order details, allocation, completion and cancellation
# ---------------------------------------------------------------------------


@never_cache
@pharmacist_required
@require_http_methods(["GET", "POST"])
def order_record(request, pk):
    """Display an order and process allocation, payment or cancellation."""
    order = get_object_or_404(
        Order.objects.select_related(
            "customer",
            "prescription",
            "processed_by",
        ),
        pk=pk,
    )

    initial = list(
        Allocation.objects.filter(item__order=order).values(
            "item",
            "batch",
            "quantity",
        )
    )

    action = (
        request.POST.get("action")
        if request.method == "POST"
        else None
    )

    formset = AllocationFormSet(
        request.POST if action == "allocate" else None,
        prefix="allocations",
        initial=initial,
        form_kwargs={"order": order},
    )

    payment_form = PaymentForm(
        request.POST if action == "complete" else None
    )

    errors = []
    status_code = 200

    if request.method == "POST":
        try:
            if action == "cancel":
                cancel_order(
                    order.pk,
                    request.POST.get("reason", ""),
                    request.user,
                )

                messages.success(
                    request,
                    "Order cancelled.",
                )

            elif action == "allocate" and formset.is_valid():
                save_allocations(
                    order.pk,
                    rows(formset),
                    request.user,
                )

                messages.success(
                    request,
                    "Batch selections saved. "
                    "Stock is checked again at completion.",
                )

            elif action == "advance":
                advance_order(
                    order.pk,
                    request.POST.get("target"),
                    request.user,
                )

                messages.success(
                    request,
                    "Order status updated.",
                )

            elif action == "complete" and payment_form.is_valid():
                complete_order(
                    order.pk,
                    user=request.user,
                    **payment_form.cleaned_data,
                )

                return redirect(
                    "pharmacist:receipt",
                    pk=order.pk,
                )

            else:
                errors.append(
                    "Check the form fields and selected action."
                )

        except (
            ValidationError,
            IntegrityError,
            OperationalError,
        ) as error:
            errors.append(error_text(error))

        if not errors:
            return redirect(
                "pharmacist:order_record",
                pk=order.pk,
            )

        status_code = 400

        # Reload the saved state after validation or a competing update.
        order.refresh_from_db()

    is_closed = order.status in (
        Order.Status.COMPLETED,
        Order.Status.CANCELLED,
    )

    target = (
        NEXT_STATUS.get(order.status)
        if order.kind == Order.Kind.ONLINE and not is_closed
        else None
    )

    payment = (
        Payment.objects.filter(order=order)
        .select_related("recorded_by")
        .first()
    )

    allocations = (
        Allocation.objects.filter(item__order=order)
        .select_related("item", "batch")
        .order_by("item_id", "batch__expiry_date", "pk")
    )

    status_events = (
        order.status_events.select_related("recorded_by")
        .order_by("recorded_at", "pk")
    )

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
            payment=payment,
            allocations=allocations,
            status_events=status_events,
            is_closed=is_closed,
            can_cancel=not is_closed,
            next_status=target,
            next_label=dict(Order.Status.choices).get(target),
            can_complete=(
                not is_closed
                and (
                    order.kind == Order.Kind.WALK_IN
                    or order.status == Order.Status.READY
                )
            ),
        ),
        status=status_code,
    )


# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------


@never_cache
@pharmacist_required
@require_safe
def receipt(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("payment", "processed_by"),
        pk=pk,
        status=Order.Status.COMPLETED,
    )

    return render(
        request,
        "pharmacist/receipt.html",
        context(
            "Receipt",
            "sales",
            order=order,
        ),
    )


# ---------------------------------------------------------------------------
# Live inventory
# ---------------------------------------------------------------------------


@never_cache
@pharmacist_required
@require_safe
def inventory_list(request):
    data = request.GET.copy()
    data.setdefault("availability", "all")

    form = InventoryFilterForm(data)

    # Batches expiring today or earlier are excluded from available stock.
    medicines = Medicine.objects.annotate(
        available=Sum(
            "batches__quantity_available",
            filter=Q(
                batches__expiry_date__gt=timezone.localdate()
            ),
            default=0,
        )
    ).prefetch_related("batches")

    filters = {}
    response_status = 200

    if form.is_valid():
        filters = form.cleaned_data

        medicines = medicines.filter(
            is_active=filters["availability"] != "archived"
        )

        if filters["q"]:
            medicines = medicines.filter(
                Q(name__icontains=filters["q"])
                | Q(strength__icontains=filters["q"])
                | Q(category_name__icontains=filters["q"])
            )

        if filters["availability"] == "low":
            medicines = medicines.filter(
                available__lte=F("reorder_level")
            )
        elif filters["availability"] == "out":
            medicines = medicines.filter(available=0)

    else:
        medicines = medicines.none()
        response_status = 400

    page = Paginator(
        medicines.order_by("name", "strength", "pk"),
        12,
    ).get_page(request.GET.get("page"))

    return render(
        request,
        "pharmacist/inventory.html",
        context(
            "Inventory",
            "inventory",
            filter_form=form,
            page_obj=page,
            filter_query=urlencode(filters),
            today=timezone.localdate(),
        ),
        status=response_status,
    )