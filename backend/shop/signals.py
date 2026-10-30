from django.db.models.signals import post_save
from django.dispatch import receiver

from inventory.models import Medicine
from .catalogue import ensure_storefront


@receiver(post_save, sender=Medicine)
def medicine_storefront(sender, instance, raw=False, **kwargs):
    if not raw:
        ensure_storefront(instance)
