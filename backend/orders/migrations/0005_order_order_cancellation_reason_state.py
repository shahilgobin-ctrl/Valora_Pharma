from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0004_orderitem_selling_unit"),
        ("prescriptions", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=(
                    (
                        models.Q(status="cancelled")
                        & ~models.Q(cancellation_reason="")
                    )
                    | (
                        ~models.Q(status="cancelled")
                        & models.Q(cancellation_reason="")
                    )
                ),
                name="order_cancellation_reason_state",
            ),
        ),
    ]