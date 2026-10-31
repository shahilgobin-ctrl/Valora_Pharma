"""Record known legacy state without inventing historical dates."""

from django.db import migrations
from django.utils import timezone


def snapshot_existing_orders(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    Event = apps.get_model("orders", "OrderStatusEvent")

    alias = schema_editor.connection.alias
    now = timezone.now()

    for order in Order.objects.using(alias).iterator():
        if not Event.objects.using(alias).filter(
            order_id=order.pk
        ).exists():
            Event.objects.using(alias).create(
                order_id=order.pk,
                status=order.status,
                recorded_at=now,
                note=(
                    "Existing status imported during upgrade; "
                    "original transition time unavailable."
                ),
            )


class Migration(migrations.Migration):
    dependencies = [
        (
            "orders",
            "0002_orderstatusevent_remove_order_order_valid_status_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(
            snapshot_existing_orders,
            migrations.RunPython.noop,
        ),
    ]