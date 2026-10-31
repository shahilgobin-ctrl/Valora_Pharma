from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory, formset_factory
from django.utils import timezone
from django.utils.text import slugify

from shop.models import Category, Product
from .models import Batch, InventoryPolicy, MedicineDetails, PurchaseOrder, PurchaseOrderLine, Supplier


class MedicineForm(forms.ModelForm):
    dosage_form = forms.CharField(max_length=80)
    price = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0.01,
        label="Selling price (Rs)")

    class Meta:
        model = Product
        fields = ["name", "category", "description", "strength", "dosage_form", "price",
                  "is_prescription"]
        labels = {"price": "Selling price (Rs)", "is_prescription": "Prescription required"}
        help_texts = {"price": ""}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            if self.instance.medicine_id:
                medicine = self.instance.medicine
                self.fields["name"].initial = medicine.name
                self.fields["description"].initial = medicine.description
                self.fields["strength"].initial = medicine.strength
                self.fields["price"].initial = medicine.selling_price
                self.fields["is_prescription"].initial = medicine.prescription_required
                self.fields["dosage_form"].initial = medicine.dosage_form


    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        return name


class BatchForm(forms.ModelForm):
    stock_source = forms.ChoiceField(choices=[("receipt", "New stock receipt"), ("opening", "Allocate existing unbatched stock")],
        initial="receipt", required=False, help_text="Allocation records existing stock without increasing the catalogue total.")
    expected_quantity = forms.IntegerField(min_value=0, widget=forms.HiddenInput, required=False)
    reason = forms.CharField(required=False, widget=forms.Textarea, help_text="Required when changing an existing quantity.")

    class Meta:
        model = Batch
        fields = ["product", "number", "quantity", "supplier", "purchase_price", "received_date", "expiry_date"]
        labels = {"product": "Medicine", "number": "Batch number", "quantity": "Units in batch", "purchase_price": "Purchase price per unit (Rs)"}
        widgets = {"received_date": forms.DateInput(attrs={"type": "date"}), "expiry_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(is_active=True)
        self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True)
        if not self.instance.pk:
            self.fields.pop("reason", None)
            self.fields.pop("expected_quantity", None)
        if self.instance.pk:
            self.fields["product"].queryset = Product.objects.all()
            self.fields.pop("stock_source", None)
            self.fields["product"].disabled = True
            self.fields["product"].help_text = "To record a different medicine, create a new batch."
            self.fields["expected_quantity"].initial = self.instance.quantity
            self.fields["expected_quantity"].required = True
            self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True) | Supplier.objects.filter(pk=self.instance.supplier_id)

    def clean(self):
        data = super().clean()
        if self.instance.pk and data.get("quantity") is not None and data["quantity"] != self.fields["expected_quantity"].initial and not data.get("reason", "").strip():
            self.add_error("reason", "Explain the quantity change before saving.")
        return data


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ["name", "contact_name", "email", "phone", "address", "is_active"]
        labels = {"name": "Company name", "is_active": "Active supplier"}
        widgets = {"phone": forms.TextInput(attrs={"type": "tel"})}


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "description"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if Category.objects.filter(slug=slugify(name)).exclude(pk=self.instance.pk).exists():
            raise ValidationError("A category with this URL already exists.")
        return name




class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ["supplier", "ordered_date", "expected_date", "notes"]
        widgets = {"ordered_date": forms.DateInput(attrs={"type": "date"}), "expected_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True)


class PurchaseLineForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrderLine
        fields = ["product", "quantity", "unit_cost"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(is_active=True)


class LinesValidation(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        rows = [f.cleaned_data for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")]
        if not rows:
            raise ValidationError("At least one medicine is required.")
        products = [r["product"].pk for r in rows]
        if len(products) != len(set(products)):
            raise ValidationError("Select each medicine once per order.")


PurchaseLines = inlineformset_factory(PurchaseOrder, PurchaseOrderLine, form=PurchaseLineForm,
    formset=LinesValidation, extra=0, can_delete=True, min_num=1, validate_min=True, max_num=100, validate_max=True)


class ReceiveForm(forms.Form):
    line_id = forms.IntegerField(widget=forms.HiddenInput)
    expected_received = forms.IntegerField(widget=forms.HiddenInput, min_value=0)
    medicine = forms.CharField(disabled=True)
    outstanding = forms.IntegerField(disabled=True)
    quantity = forms.IntegerField(min_value=0, initial=0)
    batch_number = forms.CharField(max_length=100, required=False)
    received_date = forms.DateField(initial=timezone.localdate, widget=forms.DateInput(attrs={"type": "date"}))
    expiry_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        data = super().clean()
        if data.get("quantity", 0):
            if not data.get("batch_number") or not data.get("expiry_date"):
                raise ValidationError("Batch number and expiry are required for received stock.")
            received, expiry = data.get("received_date"), data.get("expiry_date")
            if received and (received > timezone.localdate() or expiry < received):
                raise ValidationError("Check the received and expiry dates.")
        return data


ReceiveLines = formset_factory(ReceiveForm, extra=0, max_num=100, validate_max=True)


class AdjustmentForm(forms.Form):
    batch = forms.ModelChoiceField(queryset=Batch.objects.filter(is_archived=False).select_related("product"))
    expected_quantity = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    delta = forms.IntegerField(label="Quantity change", help_text="Positive to add; negative to remove.")
    reason = forms.CharField(widget=forms.Textarea)
    confirmed = forms.BooleanField(label="I confirm this stock adjustment.")

    def clean_delta(self):
        delta = self.cleaned_data["delta"]
        if not delta:
            raise ValidationError("Enter a nonzero quantity.")
        return delta


class DateRangeForm(forms.Form):
    start = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        data = super().clean()
        if data.get("start") and data.get("end") and data["end"] < data["start"]:
            raise ValidationError("End date must be on or after start date.")
        return data




class ProductInventoryForm(forms.ModelForm):
    class Meta:
        model = MedicineDetails
        fields = ["reorder_level", "expiry_warning_days"]
        labels = {"reorder_level": "Low-stock threshold", "expiry_warning_days": "Expiry warning (days)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["expiry_warning_days"].required = True
        if self.instance.expiry_warning_days is None:
            self.fields["expiry_warning_days"].initial = InventoryPolicy.objects.get(pk=1).expiry_warning_days
        if self.instance.product_id and self.instance.product.medicine_id:
            self.fields["reorder_level"].initial = self.instance.product.medicine.reorder_level


class BatchRemovalForm(forms.Form):
    expected_quantity = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    reason = forms.CharField(widget=forms.Textarea, label="Reason for removing this batch")
    confirmed = forms.BooleanField(label="Remove the remaining units from stock and keep the history")
