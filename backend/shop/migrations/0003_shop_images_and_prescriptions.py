from django.db import migrations, models


PRODUCT_SLUGS = {
    "amoxicillin", "paracetamol", "omeprazole", "metformin", "amlodipine",
    "vitamin-c", "ibuprofen", "ciprofloxacin", "atorvastatin", "cetirizine",
    "salbutamol", "vitamin-d3",
}


def use_local_product_art(apps, schema_editor):
    Product = apps.get_model("shop", "Product")
    database = schema_editor.connection.alias
    for product in Product.objects.using(database).all().iterator():
        slug = product.slug if product.slug in PRODUCT_SLUGS else "medicine"
        product.image = f"/static/shop/products/{slug}.svg"
        product.save(update_fields=["image"])


class Migration(migrations.Migration):
    dependencies = [("shop", "0002_payment")]

    operations = [
        migrations.AlterField(
            model_name="product",
            name="image",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="order",
            name="prescription_file",
            field=models.FileField(blank=True, upload_to="prescriptions/"),
        ),
        migrations.RunPython(use_local_product_art, migrations.RunPython.noop),
    ]
