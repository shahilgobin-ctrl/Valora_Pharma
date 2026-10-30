from django.db import migrations


def initialise(apps, schema_editor):
    db = schema_editor.connection.alias
    apps.get_model("manager", "InventoryPolicy").objects.using(db).get_or_create(pk=1)
    content_type, _ = apps.get_model("contenttypes", "ContentType").objects.using(db).get_or_create(
        app_label="manager", model="inventorypolicy")
    permission, _ = apps.get_model("auth", "Permission").objects.using(db).get_or_create(
        content_type=content_type, codename="access_manager", defaults={"name": "Access Pharmacy Manager workspace"})
    group, _ = apps.get_model("auth", "Group").objects.using(db).get_or_create(name="Pharmacy Managers")
    group.permissions.add(permission)
    Product = apps.get_model("shop", "Product")
    Details = apps.get_model("manager", "MedicineDetails")
    for product in Product.objects.using(db).all().iterator():
        dosage = product.strength.rsplit(" - ", 1)[1] if " - " in product.strength else ""
        Details.objects.using(db).get_or_create(product_id=product.pk, defaults={"dosage_form": dosage})


class Migration(migrations.Migration):
    dependencies = [("manager", "0001_initial"), ("auth", "0012_alter_user_first_name_max_length")]
    operations = [migrations.RunPython(initialise, migrations.RunPython.noop)]
