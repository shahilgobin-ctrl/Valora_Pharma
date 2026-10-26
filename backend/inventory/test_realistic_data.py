"""Dataset guards, repeatability and accounting consistency."""

from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Sum
from django.test import TestCase, override_settings
from django.utils import timezone

from inventory.models import Batch, Medicine
from inventory.management.commands.seed_realistic_data import clear_operational_records
from orders.models import Allocation, Order, Payment, StockMovement
from prescriptions.models import Prescription


@override_settings(DEBUG=True)
class RealisticDatasetTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        override = override_settings(MEDIA_ROOT=self.directory.name)
        override.enable()
        self.addCleanup(override.disable)
        self.staff = get_user_model().objects.create_user(
            email="fixture-staff@example.invalid", account_type="staff"
        )
        group, _ = Group.objects.get_or_create(name="Pharmacist")
        self.staff.groups.add(group)

    def seed(self, **kwargs):
        call_command(
            "seed_realistic_data",
            pharmacist=self.staff.email,
            stdout=StringIO(),
            **kwargs
        )

    def test_dataset_has_consistent_totals_allocations_and_stock(self):
        self.seed()
        self.assertEqual(Medicine.objects.count(), 25)
        self.assertEqual(Batch.objects.count(), 52)
        self.assertEqual(Order.objects.count(), 36)
        self.assertEqual(
            get_user_model().objects.filter(account_type="customer").count(), 18
        )
        self.assertEqual(
            set(Order.objects.values_list("status", flat=True)),
            {"pending", "confirmed", "preparing", "ready", "completed", "cancelled"},
        )
        self.assertEqual(
            set(Prescription.objects.values_list("status", flat=True)),
            {"pending", "approved", "rejected"},
        )
        for order in Order.objects.all():
            self.assertEqual(
                order.total_amount, sum(item.line_total for item in order.items.all())
            )
            self.assertEqual(order.status_events.last().status, order.status)
            self.assertGreaterEqual(
                order.status_events.first().recorded_at, order.created_at
            )
            if order.status == "completed":
                self.assertEqual(order.payment.amount, order.total_amount)
                self.assertEqual(order.payment.recorded_at, order.completed_at)
                for item in order.items.all():
                    self.assertEqual(
                        item.allocations.aggregate(total=Sum("quantity"))["total"],
                        item.quantity,
                    )
                    for allocation in item.allocations.all():
                        self.assertEqual(
                            allocation.movement.quantity, allocation.quantity
                        )
            else:
                self.assertFalse(Payment.objects.filter(order=order).exists())
                self.assertFalse(
                    StockMovement.objects.filter(allocation__item__order=order).exists()
                )
        self.assertTrue(Batch.objects.filter(quantity_available=0).exists())
        self.assertTrue(
            Batch.objects.filter(expiry_date__lte=timezone.localdate()).exists()
        )
        self.assertFalse(
            Allocation.objects.filter(
                batch__expiry_date__lte=timezone.localdate()
            ).exists()
        )
        for batch in Batch.objects.exclude(batch_number__startswith="VP-QUARANTINE"):
            index = int(batch.batch_number.split("-")[2]) - 1
            original = 0 if index == 13 else (3 if index == 14 else 180 + index * 7)
            dispensed = (
                StockMovement.objects.filter(allocation__batch=batch).aggregate(
                    total=Sum("quantity")
                )["total"]
                or 0
            )
            self.assertEqual(batch.quantity_available + dispensed, original)
        for rx in Prescription.objects.all():
            self.assertTrue(rx.document.storage.exists(rx.document.name))
            if rx.reviewed_at:
                self.assertGreaterEqual(rx.reviewed_at, rx.uploaded_at)

    def test_rerun_preserves_rows_files_stock_and_decisions(self):
        self.seed()
        before = list(Batch.objects.values_list("pk", "quantity_available"))
        files = sorted(Path(self.directory.name).rglob("*.pdf"))
        self.seed()
        self.assertEqual(Order.objects.count(), 36)
        self.assertEqual(
            list(Batch.objects.values_list("pk", "quantity_available")), before
        )
        self.assertEqual(sorted(Path(self.directory.name).rglob("*.pdf")), files)

    def test_failure_rolls_back_rows_and_cleans_created_files(self):
        with patch(
            "inventory.management.commands.seed_realistic_data.create_order",
            side_effect=CommandError("failure"),
        ):
            with self.assertRaises(CommandError):
                self.seed()
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Medicine.objects.exists())
        self.assertFalse(Prescription.objects.exists())
        self.assertEqual(list(Path(self.directory.name).rglob("*.pdf")), [])
        self.assertTrue(get_user_model().objects.filter(pk=self.staff.pk).exists())

    @override_settings(DEBUG=False)
    def test_refuses_production(self):
        with self.assertRaises(CommandError):
            self.seed()

    def test_requires_existing_pharmacist(self):
        self.staff.groups.clear()
        with self.assertRaises(CommandError):
            self.seed()
        self.assertFalse(Medicine.objects.exists())

    def test_existing_business_data_is_not_silently_overwritten(self):
        medicine = Medicine.objects.create(
            name="Existing", strength="1", dosage_form="Tablet", selling_price=1
        )
        with self.assertRaises(CommandError):
            self.seed()
        self.assertTrue(Medicine.objects.filter(pk=medicine.pk).exists())

    def test_replacement_requires_backup_before_any_deletion(self):
        self.seed()
        with self.assertRaises(CommandError):
            self.seed(replace_development_data=True)
        self.assertEqual(Order.objects.count(), 36)

    def test_clear_business_records_preserves_accounts_and_documents(self):
        self.seed()
        count = get_user_model().objects.count()
        files = sorted(Path(self.directory.name).rglob("*.pdf"))
        clear_operational_records()
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Medicine.objects.exists())
        self.assertEqual(get_user_model().objects.count(), count)
        self.assertEqual(sorted(Path(self.directory.name).rglob("*.pdf")), files)

    def test_failed_replacement_restores_original_business_records(self):
        self.seed()
        original_ids = list(Order.objects.values_list("pk", flat=True))
        with patch(
            "inventory.management.commands.seed_realistic_data.backup_database",
            return_value="verified-test-backup",
        ), patch(
            "inventory.management.commands.seed_realistic_data.Command.build_dataset",
            side_effect=CommandError("failure"),
        ):
            with self.assertRaises(CommandError):
                self.seed(replace_development_data=True, backup="test.sqlite3")
        self.assertEqual(list(Order.objects.values_list("pk", flat=True)), original_ids)
        self.assertEqual(Payment.objects.count(), 12)
