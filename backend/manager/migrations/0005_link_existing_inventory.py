import django.db.models.deletion
from django.db import migrations, models


def link_existing_inventory(apps, schema_editor):
    alias = schema_editor.connection.alias
    ManagedBatch = apps.get_model("manager", "Batch")
    InventoryBatch = apps.get_model("inventory", "Batch")
    Supplier = apps.get_model("manager", "Supplier")
    Product = apps.get_model("shop", "Product")
    if ManagedBatch.objects.using(alias).filter(inventory_batch__isnull=True).exists():
        raise RuntimeError("Manager batches need explicit review before linking to inventory batches.")
    for batch in InventoryBatch.objects.using(alias).all().iterator():
        product = Product.objects.using(alias).filter(medicine_id=batch.medicine_id).first()
        if product is None:
            raise RuntimeError(f"Medicine {batch.medicine_id} lacks an explicit storefront link.")
        supplier, _ = Supplier.objects.using(alias).get_or_create(name=batch.supplier_name)
        ManagedBatch.objects.using(alias).get_or_create(
            inventory_batch_id=batch.pk,
            defaults={"product_id": product.pk, "supplier_id": supplier.pk,
                "number": batch.batch_number, "quantity": batch.quantity_available,
                "purchase_price": batch.purchase_price, "received_date": batch.received_date,
                "expiry_date": batch.expiry_date},
        )


class Migration(migrations.Migration):
    dependencies = [("manager", "0004_batch_is_archived_and_more"),
                    ("shop", "0006_product_medicine"),
                    ("inventory", "0002_medicine_selling_unit")]
    operations = [
        migrations.AddField(model_name="batch", name="inventory_batch",
            field=models.OneToOneField(blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="manager_record", to="inventory.batch")),
        migrations.RunPython(link_existing_inventory, migrations.RunPython.noop),
    ]
