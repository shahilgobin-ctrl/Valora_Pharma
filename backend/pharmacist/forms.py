"""Forms, filters and formsets for pharmacist workflows."""

from django import forms
from django.forms import BaseFormSet, formset_factory
from django.utils import timezone

from accounts.models import User
from inventory.models import Batch, Medicine
from orders.models import Order, OrderItem, Payment
from prescriptions.models import Prescription


# ---------------------------------------------------------------------------
# Prescription review and queue filters
# ---------------------------------------------------------------------------


class PrescriptionReviewForm(forms.Form):
    decision = forms.ChoiceField(
        choices=[
            (Prescription.Status.APPROVED, "Approve"),
            (Prescription.Status.REJECTED, "Reject"),
        ],
        widget=forms.HiddenInput,
    )

    rejection_reason = forms.CharField(
        required=False,
        max_length=1000,
        strip=True,
        label="Rejection reason",
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Explain why the prescription is rejected.",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        decision = cleaned_data.get("decision")
        reason = cleaned_data.get("rejection_reason", "")

        if decision == Prescription.Status.REJECTED and not reason:
            self.add_error(
                "rejection_reason",
                "Enter a reason for rejecting this prescription.",
            )

        if decision == Prescription.Status.APPROVED:
            cleaned_data["rejection_reason"] = ""

        return cleaned_data


class PrescriptionQueueFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        max_length=100,
        strip=True,
        label="Search prescriptions",
        widget=forms.TextInput(
            attrs={
                "type": "search",
                "placeholder": "Customer name, email or RX reference",
            }
        ),
    )

    status = forms.ChoiceField(
        choices=[
            (Prescription.Status.PENDING, "Pending"),
            (Prescription.Status.APPROVED, "Approved"),
            (Prescription.Status.REJECTED, "Rejected"),
            ("all", "All statuses"),
        ],
        label="Status",
    )


# ---------------------------------------------------------------------------
# Walk-in sale details and medicine rows
# ---------------------------------------------------------------------------


class SaleForm(forms.Form):
    submission_key = forms.UUIDField(widget=forms.HiddenInput)

    customer = forms.ModelChoiceField(
    queryset=User.objects.filter(
        account_type=User.AccountType.CUSTOMER,
        is_active=True,
    ),
    required=False,
    )

    prescription = forms.ModelChoiceField(
    queryset=Prescription.objects.filter(
        status=Prescription.Status.APPROVED,
    ),
    required=False,
    )

    contact_name = forms.CharField(
        max_length=150,
        required=False,
    )

    contact_phone = forms.RegexField(
        r"^\+?[0-9]{7,15}$",
        max_length=16,
        required=False,
        help_text="7–15 digits, optional leading +.",
    )

    def clean(self):
        data = super().clean()
        prescription = data.get("prescription")
        customer = data.get("customer")

        if prescription and (
            not customer or prescription.customer_id != customer.pk
        ):
            self.add_error(
                "prescription",
                "Select the customer who owns this prescription.",
            )

        return data


class SaleLineForm(forms.Form):
    medicine = forms.ModelChoiceField(
        queryset=Medicine.objects.filter(is_active=True)
    )

    quantity = forms.IntegerField(
        min_value=1,
        max_value=10000,
    )


class RequiredRows(BaseFormSet):
    """Require at least one populated row that is not marked for deletion."""

    def clean(self):
        if any(self.errors):
            return

        rows = [
            form.cleaned_data
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]

        if not rows:
            raise forms.ValidationError("Add at least one row.")


SaleLineFormSet = formset_factory(
    SaleLineForm,
    formset=RequiredRows,
    extra=3,
    can_delete=True,
    max_num=50,
    validate_max=True,
    absolute_max=60,
)


# ---------------------------------------------------------------------------
# Batch allocation
# ---------------------------------------------------------------------------


class AllocationForm(forms.Form):
    item = forms.ModelChoiceField(queryset=OrderItem.objects.none())
    batch = forms.ModelChoiceField(queryset=Batch.objects.none())

    quantity = forms.IntegerField(
        min_value=1,
        max_value=10000,
    )

    def __init__(self, *args, order, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["item"].queryset = order.items.all()

        # Only offer available, unexpired batches for medicines in this order.
        self.fields["batch"].queryset = Batch.objects.filter(
            medicine_id__in=order.items.values("medicine_id"),
            medicine__is_active=True,
            expiry_date__gt=timezone.localdate(),
            quantity_available__gt=0,
        ).select_related("medicine")


AllocationFormSet = formset_factory(
    AllocationForm,
    formset=RequiredRows,
    extra=2,
    can_delete=True,
    max_num=100,
    validate_max=True,
    absolute_max=110,
)


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------


class PaymentForm(forms.Form):
    method = forms.ChoiceField(choices=Payment.Method.choices)

    cash_tendered = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        required=False,
    )

    def clean(self):
        data = super().clean()

        if (
            data.get("method") == "cash"
            and data.get("cash_tendered") is None
        ):
            self.add_error(
                "cash_tendered",
                "Enter the cash tendered.",
            )

        return data


# ---------------------------------------------------------------------------
# Order and inventory filters
# ---------------------------------------------------------------------------


class OrderFilterForm(forms.Form):
    q = forms.CharField(
        max_length=100,
        required=False,
        label="Customer or order reference",
    )

    status = forms.ChoiceField(
        choices=[
            ("open", "Open orders"),
            ("all", "All statuses"),
            *Order.Status.choices,
        ]
    )

    kind = forms.ChoiceField(
    choices=[
        *Order.Kind.choices,
        ("all", "All orders"),
    ]
    )   


class InventoryFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        max_length=100,
        label="Medicine or category",
    )

    availability = forms.ChoiceField(
        choices=[
            ("all", "All active medicines"),
            ("low", "At or below reorder level"),
            ("out", "Out of stock"),
            ("archived", "Archived medicines"),
        ]
    )