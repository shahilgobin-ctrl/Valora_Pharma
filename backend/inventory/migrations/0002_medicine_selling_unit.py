from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="medicine",
            name="selling_unit",
            field=models.CharField(
                default="unit",
                max_length=80,
            ),
        ),
    ]