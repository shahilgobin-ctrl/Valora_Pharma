"""Promote approved Home photos to the shared catalogue image field."""
from django.db import migrations


def share_catalogue_artwork(apps, schema_editor):
    alias = schema_editor.connection.alias
    Artwork = apps.get_model("pages", "HomepageProductImage")
    Product = apps.get_model("shop", "Product")
    for artwork in Artwork.objects.using(alias).exclude(image="").iterator():
        Product.objects.using(alias).filter(pk=artwork.product_id).update(image=artwork.image)


class Migration(migrations.Migration):
    dependencies = [("pages", "0003_restore_home_artwork")]
    operations = [migrations.RunPython(share_catalogue_artwork, migrations.RunPython.noop)]
