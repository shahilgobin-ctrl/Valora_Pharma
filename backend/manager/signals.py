"""Keep manager metadata aligned when pharmacist or inventory edits a batch."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from inventory.models import Batch as InventoryBatch
from shop.models import Product
from .models import Batch, Supplier


@receiver(post_save, sender=InventoryBatch)
def mirror_physical_batch(sender, instance, raw=False, **kwargs):
    if raw:
        return
    product = Product.objects.filter(medicine_id=instance.medicine_id).first()
    if product is None:
        return
    supplier, _ = Supplier.objects.get_or_create(name=instance.supplier_name)
    existing = Batch.objects.filter(inventory_batch=instance).first()
    if existing is None:
        existing = Batch.objects.filter(product=product, number=instance.batch_number).first()
    values = dict(inventory_batch=instance, product=product, supplier=supplier,
        number=instance.batch_number, quantity=instance.quantity_available,
        purchase_price=instance.purchase_price, received_date=instance.received_date,
        expiry_date=instance.expiry_date)
    if existing:
        Batch.objects.filter(pk=existing.pk).update(**values)
    else:
        Batch.objects.create(**values)
