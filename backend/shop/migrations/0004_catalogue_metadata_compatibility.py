"""Adopt existing catalogue metadata without importing Home pages or modifying data."""
from django.db import migrations, models


def adopt_metadata_columns(apps, schema_editor):
    for model_name, fields in [("Category", ("image", "display_order")), ("Product", ("homepage_order",))]:
        model = apps.get_model("shop", model_name)
        with schema_editor.connection.cursor() as cursor:
            columns = {column.name for column in schema_editor.connection.introspection.get_table_description(cursor, model._meta.db_table)}
        for name in fields:
            field = model._meta.get_field(name)
            if field.column not in columns:
                schema_editor.add_field(model, field)


class Migration(migrations.Migration):
    dependencies = [("shop", "0003_shop_images_and_prescriptions")]
    operations = [
        migrations.SeparateDatabaseAndState(state_operations=[
            migrations.AddField(model_name="category", name="image", field=models.CharField(blank=True, max_length=500)),
            migrations.AddField(model_name="category", name="display_order", field=models.PositiveIntegerField(default=100)),
            migrations.AddField(model_name="product", name="homepage_order", field=models.PositiveIntegerField(default=100)),
        ]),
        migrations.RunPython(adopt_metadata_columns, migrations.RunPython.noop),
    ]
