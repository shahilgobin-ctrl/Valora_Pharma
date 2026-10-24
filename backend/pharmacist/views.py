"""Protected pharmacist views and development previews."""

from functools import wraps
from pathlib import Path
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Q

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_http_methods, require_safe

from accounts.models import User
from prescriptions.models import Prescription

from .forms import PrescriptionQueueFilterForm, PrescriptionReviewForm

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
        "key": "sales",
        "route": "pharmacist:sale_form",
        "label": "New walk-in sale",
    },
]

PAGES = {
    "dashboard": ("Dashboard", "dashboard"),
    "prescription_queue": ("Prescription queue", "prescriptions"),
    "prescription_review": ("Prescription review", "prescriptions"),
    "order_queue": ("Online orders", "orders"),
    "order_detail": ("Order details", "orders"),
    "sale_form": ("New walk-in sale", "sales"),
    "sale_receipt": ("Sample receipt", "sales"),
}


def pharmacist_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user

        # Pharmacy roles are separate from Django admin access.
        if (
            not user.is_active
            or user.account_type != User.AccountType.STAFF
            or not user.groups.filter(name="Pharmacist").exists()
        ):
            raise PermissionDenied("Only pharmacists can access this page.")

        return view_func(request, *args, **kwargs)

    return login_required(
        wrapper,
        login_url="accounts:staff_login",
    )


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
            prescriptions = prescriptions.filter(status=selected_status)

        if search_query:
            search_conditions = (
                Q(customer__first_name__icontains=search_query)
                | Q(customer__last_name__icontains=search_query)
                | Q(customer__email__icontains=search_query)
            )

            # Also support a full name such as "Demo Customer".
            name_parts = search_query.split()
            if len(name_parts) > 1:
                full_name_conditions = Q()
                for part in name_parts:
                    full_name_conditions &= Q(customer__first_name__icontains=part) | Q(
                        customer__last_name__icontains=part
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

    # Pending work is oldest first; history is newest submitted first.
    if selected_status == Prescription.Status.PENDING:
        prescriptions = prescriptions.order_by("uploaded_at", "pk")
    else:
        prescriptions = prescriptions.order_by("-uploaded_at", "-pk")

    paginator = Paginator(prescriptions, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Preserve validated filters in pagination links.
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
    form = PrescriptionReviewForm(request.POST if request.method == "POST" else None)
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
                or not prescription.document.storage.exists(prescription.document.name)
            ):
                form.add_error(
                    None,
                    "The document is missing. Approval is not possible.",
                )
                response_status = 400
            else:
                prescription.status = decision
                prescription.rejection_reason = form.cleaned_data["rejection_reason"]
                prescription.reviewed_by = request.user
                prescription.reviewed_at = timezone.now()

                try:
                    # The saved document is unchanged by this operation.
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

        # Show saved values after validation errors or a competing review.
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
            "document_extension": Path(prescription.document.name or "").suffix.lower(),
        },
        status=response_status,
    )


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

    # Permit embedding within our application only.
    response["Content-Security-Policy"] = "frame-ancestors 'self'"
    response["X-Content-Type-Options"] = "nosniff"

    return response
