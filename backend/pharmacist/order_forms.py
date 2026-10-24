from django import forms
from django.forms import BaseFormSet, formset_factory
from django.utils import timezone

from accounts.models import User
from inventory.models import Batch, Medicine
from orders.models import OrderItem, Payment
from prescriptions.models import Prescription


class SaleForm(forms.Form):
    submission_key = forms.UUIDField(widget=forms.HiddenInput)
    customer = forms.ModelChoiceField(
        queryset=User.objects.filter(account_type="customer"), required=False
    )
    prescription = forms.ModelChoiceField(
        queryset=Prescription.objects.filter(status="approved"), required=False
    )
    contact_name = forms.CharField(max_length=150, required=False)
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
        if prescription and (not customer or prescription.customer_id != customer.pk):
            self.add_error(
                "prescription", "Select the customer who owns this prescription."
            )
        return data


class SaleLineForm(forms.Form):
    medicine = forms.ModelChoiceField(queryset=Medicine.objects.filter(is_active=True))
    quantity = forms.IntegerField(min_value=1, max_value=10000)


class RequiredRows(BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        rows = [
            f.cleaned_data
            for f in self.forms
            if f.cleaned_data and not f.cleaned_data.get("DELETE")
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


class AllocationForm(forms.Form):
    item = forms.ModelChoiceField(queryset=OrderItem.objects.none())
    batch = forms.ModelChoiceField(queryset=Batch.objects.none())
    quantity = forms.IntegerField(min_value=1, max_value=10000)

    def __init__(self, *args, order, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = order.items.all()
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


class PaymentForm(forms.Form):
    method = forms.ChoiceField(choices=Payment.Method.choices)
    cash_tendered = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False
    )

    def clean(self):
        data = super().clean()
        if data.get("method") == "cash" and data.get("cash_tendered") is None:
            self.add_error("cash_tendered", "Enter the cash tendered.")
        return data
