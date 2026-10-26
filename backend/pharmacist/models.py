"""Shared domain model ownership will be agreed before database work."""
"""Pharmacy details shared by the interface and receipts."""

from django.db import models
from django.db.models import Q


class PharmacyProfile(models.Model):
    """Store one editable profile for the pharmacy."""

    id = models.PositiveSmallIntegerField(
        primary_key=True,
        default=1,
        editable=False,
    )
    name = models.CharField(max_length=150)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    receipt_footer = models.CharField(max_length=250, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(id=1),
                name="single_pharmacy_profile",
            ),
        ]

    def __str__(self):
        return self.name