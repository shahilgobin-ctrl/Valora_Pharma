"""Read-only, live inventory for dispensing staff."""

from urllib.parse import urlencode

from django import forms
from django.core.paginator import Paginator
from django.db.models import F, Q, Sum
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from inventory.models import Medicine
from .order_views import context
from .views import pharmacist_required


class InventoryFilterForm(forms.Form):
    q = forms.CharField(required=False, max_length=100, label="Medicine or category")
    availability = forms.ChoiceField(
        choices=[
            ("all", "All active medicines"),
            ("low", "At or below reorder level"),
            ("out", "Out of stock"),
            ("archived", "Archived medicines"),
        ]
    )


@never_cache
@pharmacist_required
@require_safe
def inventory_list(request):
    data = request.GET.copy()
    data.setdefault("availability", "all")
    form = InventoryFilterForm(data)
    medicines = Medicine.objects.annotate(
        available=Sum(
            "batches__quantity_available",
            filter=Q(batches__expiry_date__gt=timezone.localdate()),
            default=0,
        )
    ).prefetch_related("batches")
    filters = {}
    response_status = 200
    if form.is_valid():
        filters = form.cleaned_data
        medicines = medicines.filter(is_active=filters["availability"] != "archived")
        if filters["q"]:
            medicines = medicines.filter(
                Q(name__icontains=filters["q"])
                | Q(strength__icontains=filters["q"])
                | Q(category_name__icontains=filters["q"])
            )
        if filters["availability"] == "low":
            medicines = medicines.filter(available__lte=F("reorder_level"))
        elif filters["availability"] == "out":
            medicines = medicines.filter(available=0)
    else:
        medicines = medicines.none()
        response_status = 400
    page = Paginator(medicines.order_by("name", "strength", "pk"), 12).get_page(
        request.GET.get("page")
    )
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
