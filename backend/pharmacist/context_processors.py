"""Provide saved pharmacy details to every template."""

from .models import PharmacyProfile
from django.utils.functional import SimpleLazyObject


def pharmacy_profile(request):
    """Return the single pharmacy profile, when configured."""
    return {
        "pharmacy": SimpleLazyObject(lambda: PharmacyProfile.objects.first()),
    }