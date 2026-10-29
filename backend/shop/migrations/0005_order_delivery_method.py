from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("shop", "0004_product_photographs")]

    operations = [
        migrations.AddField(
            model_name="order",
            name="delivery_method",
            field=models.CharField(
                choices=[("delivery", "Delivery"), ("pickup", "Pick up")],
                default="delivery",
                max_length=10,
            ),
        ),
    ]
