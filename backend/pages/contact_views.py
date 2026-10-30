from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import ContactForm


@require_http_methods(["GET", "HEAD", "POST"])
def contact(request):
    form = ContactForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Thank you. Your message has been saved for our team to review.")
        return redirect("pages:contact")
    return render(request, "pages/contact.html", {"active_page": "contact", "form": form})
