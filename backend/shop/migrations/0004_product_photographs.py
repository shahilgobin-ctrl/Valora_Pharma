from django.db import migrations


PRODUCT_SLUGS = {
    "amoxicillin", "paracetamol", "omeprazole", "metformin", "amlodipine",
    "vitamin-c", "ibuprofen", "ciprofloxacin", "atorvastatin", "cetirizine",
    "salbutamol", "vitamin-d3",
}


def use_local_product_photographs(apps, schema_editor):
    Product = apps.get_model("shop", "Product")
    database = schema_editor.connection.alias
    for product in Product.objects.using(database).all().iterator():
        if product.slug in PRODUCT_SLUGS:
            product.image = f"/static/shop/products/{product.slug}.jpg"
            product.save(update_fields=["image"])


class Migration(migrations.Migration):
    dependencies = [("shop", "0003_shop_images_and_prescriptions")]

    operations = [migrations.RunPython(use_local_product_photographs, migrations.RunPython.noop)]
