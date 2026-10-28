import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                    ("name", models.CharField(max_length=100, unique=True)),
                    ("slug", models.SlugField(blank=True, max_length=110, unique=True)),
                    ("description", models.TextField(blank=True))],
        ),
        migrations.CreateModel(
            name="Cart",
            fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                    ("updated_at", models.DateTimeField(auto_now=True)),
                    ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="shop_cart", to=settings.AUTH_USER_MODEL))],
        ),
        migrations.CreateModel(
            name="Product",
            fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                    ("name", models.CharField(max_length=160)),
                    ("slug", models.SlugField(blank=True, max_length=180, unique=True)),
                    ("description", models.TextField(blank=True)),
                    ("strength", models.CharField(blank=True, max_length=100)),
                    ("price", models.PositiveIntegerField(help_text="Price in Rs")),
                    ("stock_quantity", models.PositiveIntegerField(default=0)),
                    ("image", models.URLField(blank=True)),
                    ("is_prescription", models.BooleanField(default=False)),
                    ("is_active", models.BooleanField(default=True)),
                    ("created_at", models.DateTimeField(auto_now_add=True)),
                    ("category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="products", to="shop.category"))],
        ),
        migrations.CreateModel(
            name="Order",
            fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                    ("total", models.PositiveIntegerField()),
                    ("status", models.CharField(choices=[("placed", "Placed"), ("processing", "Processing"), ("completed", "Completed")], default="placed", max_length=20)),
                    ("created_at", models.DateTimeField(auto_now_add=True)),
                    ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="shop_orders", to=settings.AUTH_USER_MODEL))],
        ),
        migrations.CreateModel(
            name="OrderItem",
            fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                    ("quantity", models.PositiveIntegerField()),
                    ("unit_price", models.PositiveIntegerField()),
                    ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="shop.order")),
                    ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="shop.product"))],
        ),
        migrations.CreateModel(
            name="CartItem",
            fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                    ("quantity", models.PositiveIntegerField(default=1)),
                    ("cart", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="shop.cart")),
                    ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="shop.product"))],
            options={"constraints": [models.UniqueConstraint(fields=("cart", "product"), name="shop_cart_item_unique_product")]},
        ),
    ]
