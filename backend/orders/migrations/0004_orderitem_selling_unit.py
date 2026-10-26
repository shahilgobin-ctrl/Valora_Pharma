from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0003_legacy_history"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderitem",
            name="selling_unit",
            field=models.CharField(
                default="unit",
                max_length=80,
            ),
        ),
    ]