from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from .models import Batch, Medicine


class InventoryValidationTests(TestCase):
    def setUp(self):
        self.medicine = Medicine.objects.create(
            name="Demo", strength="1 mg", dosage_form="Tablet", selling_price=2
        )

    def test_positive_price_required(self):
        self.medicine.selling_price = 0
        with self.assertRaises(ValidationError):
            self.medicine.full_clean()

    def test_blank_name_rejected(self):
        self.medicine.name = "   "
        with self.assertRaises(ValidationError):
            self.medicine.full_clean()

    def test_batch_dates_and_nonnegative_stock(self):
        batch = Batch(
            medicine=self.medicine,
            batch_number="B",
            supplier_name="Supplier",
            expiry_date=timezone.localdate(),
            purchase_price=1,
        )
        with self.assertRaises(ValidationError):
            batch.full_clean()
        batch.expiry_date += timedelta(days=30)
        batch.quantity_available = -1
        with self.assertRaises(ValidationError):
            batch.full_clean()

    def test_duplicate_batch_number_rejected_for_same_medicine(self):
        values = dict(
            medicine=self.medicine,
            batch_number="B",
            supplier_name="Supplier",
            expiry_date=timezone.localdate() + timedelta(days=30),
            purchase_price=1,
        )
        Batch.objects.create(**values)
        with self.assertRaises(ValidationError):
            Batch(**values).full_clean()
