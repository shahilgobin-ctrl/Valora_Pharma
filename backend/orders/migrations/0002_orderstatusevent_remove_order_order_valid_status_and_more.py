import django.db.models.deletion
import django.utils.timezone

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0001_initial"),
        ("prescriptions", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OrderStatusEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("confirmed", "Confirmed"),
                            ("preparing", "Preparing"),
                            ("ready", "Ready for pickup"),
                            ("completed", "Completed"),
                            ("cancelled", "Cancelled"),
                        ],
                        max_length=12,
                    ),
                ),
                (
                    "recorded_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now
                    ),
                ),
                (
                    "note",
                    models.CharField(
                        blank=True,
                        max_length=500,
                    ),
                ),
            ],
            options={
                "ordering": ["recorded_at", "pk"],
            },
        ),
        migrations.RemoveConstraint(
            model_name="order",
            name="order_valid_status",
        ),
        migrations.AddField(
            model_name="order",
            name="cancellation_reason",
            field=models.CharField(
                blank=True,
                max_length=500,
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("confirmed", "Confirmed"),
                    ("preparing", "Preparing"),
                    ("ready", "Ready for pickup"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=12,
            ),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        "pending",
                        "confirmed",
                        "preparing",
                        "ready",
                        "completed",
                        "cancelled",
                    ]
                ),
                name="order_valid_status",
            ),
        ),
        migrations.AddField(
            model_name="orderstatusevent",
            name="order",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="status_events",
                to="orders.order",
            ),
        ),
        migrations.AddField(
            model_name="orderstatusevent",
            name="recorded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]