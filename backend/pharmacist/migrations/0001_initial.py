from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="PharmacyProfile",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "name",
                    models.CharField(max_length=150),
                ),
                (
                    "address",
                    models.TextField(blank=True),
                ),
                (
                    "phone",
                    models.CharField(blank=True, max_length=20),
                ),
                (
                    "email",
                    models.EmailField(blank=True, max_length=254),
                ),
                (
                    "receipt_footer",
                    models.CharField(blank=True, max_length=250),
                ),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(id=1),
                        name="single_pharmacy_profile",
                    ),
                ],
            },
        ),
    ]