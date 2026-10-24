from django import forms

from prescriptions.models import Prescription


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