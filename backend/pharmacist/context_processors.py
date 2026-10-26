"""Provide saved pharmacy details to every template."""

from .models import PharmacyProfile


def pharmacy_profile(request):
    """Return the single pharmacy profile, when configured."""
    return {
        "pharmacy": PharmacyProfile.objects.first(),
    }