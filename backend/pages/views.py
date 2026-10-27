from django.shortcuts import render
from django.views.decorators.http import require_safe


@require_safe
def about(request):
    """Display fixed company information without querying a database."""
    return render(request, "pages/about.html", {"active_page": "about"})
