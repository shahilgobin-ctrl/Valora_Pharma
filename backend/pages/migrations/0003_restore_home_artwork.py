"""Restore missing Home artwork after a late catalogue import.

Only Home presentation records are created. Existing overrides and all shared
catalogue, inventory, price and stock values remain unchanged.
"""
from django.db import migrations
from django.contrib.staticfiles import finders


def restore_home_artwork(apps, schema_editor):
    alias = schema_editor.connection.alias
    Product = apps.get_model("shop", "Product")
    Artwork = apps.get_model("pages", "HomepageProductImage")
    featured = {
        "amoxicillin": "home/photos/capsules.jpg",
        "paracetamol": "home/photos/paracetamol-home.jpg",
        "vitamin-c": "home/photos/vitamins.jpg",
        "omeprazole": "home/photos/blister-packs.jpg",
    }
    for product in Product.objects.using(alias).all().iterator():
        image = featured.get(product.slug, f"shop/products/{product.slug}.jpg")
        if finders.find(image):
            Artwork.objects.using(alias).get_or_create(
                product_id=product.pk, defaults={"image": image}
            )


class Migration(migrations.Migration):
    dependencies = [("pages", "0002_contact_message")]
    operations = [migrations.RunPython(restore_home_artwork, migrations.RunPython.noop)]
