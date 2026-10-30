import re

from django import forms

from .models import ContactMessage


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ["full_name", "email", "phone", "subject", "message"]
        labels = {
            "full_name": "Full Name",
            "email": "Email Address",
            "phone": "Phone Number",
            "subject": "Subject",
            "message": "Message",
        }
        widgets = {
            "full_name": forms.TextInput(attrs={"placeholder": "Your full name", "autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"placeholder": "Your email address", "autocomplete": "email"}),
            "phone": forms.TextInput(attrs={
                "type": "tel", "placeholder": "Your phone number", "autocomplete": "tel",
            }),
            "subject": forms.TextInput(attrs={"placeholder": "Your subject"}),
            "message": forms.Textarea(attrs={"placeholder": "Tell us how we can help...", "rows": 4}),
        }

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if phone and (not re.fullmatch(r"\+?[0-9 ()-]+", phone) or not 7 <= len(re.sub(r"\D", "", phone)) <= 15):
            raise forms.ValidationError("Enter a valid phone number, including the country code if needed.")
        return phone
