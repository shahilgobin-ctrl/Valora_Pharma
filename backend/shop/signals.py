from django.db.models.signals import post_save
from django.dispatch import receiver

from inventory.models import Medicine
from .catalogue import ensure_storefront


@receiver(post_save, sender=Medicine)
def medicine_storefront(sender, instance, raw=False, **kwargs):
    if not raw:
        product = ensure_storefront(instance)
        from .models import Product
        Product.objects.filter(pk=product.pk).update(
            name=instance.name, description=instance.description,
            strength=instance.strength, is_active=instance.is_active,
        )
