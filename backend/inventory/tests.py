"""Validation tests for medicines and inventory batches."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from .models import Batch, Medicine


class InventoryValidationTests(TestCase):
    def setUp(self):
        self.medicine = Medicine.objects.create(
            name="Paracetamol",
            strength="500 mg",
            dosage_form="Tablet",
            selling_price="3.50",
        )

    # Medicine validation.

    def test_positive_price_required(self):
        self.medicine.selling_price = 0

        with self.assertRaises(ValidationError):
            self.medicine.full_clean()

    def test_blank_name_rejected(self):
        self.medicine.name = "   "

        with self.assertRaises(ValidationError):
            self.medicine.full_clean()

    # Batch validation.

    def test_batch_dates_and_nonnegative_stock(self):
        today = timezone.localdate()

        batch = Batch(
            medicine=self.medicine,
            batch_number="BATCH-001",
            supplier_name="Test Supplier",
            received_date=today,
            expiry_date=today,
            purchase_price="2.00",
        )

        # Expiry must be later than the receipt date.
        with self.assertRaises(ValidationError):
            batch.full_clean()

        batch.expiry_date = today + timedelta(days=30)
        batch.quantity_available = -1

        # Available stock cannot be negative.
        with self.assertRaises(ValidationError):
            batch.full_clean()

    def test_duplicate_batch_number_rejected_for_same_medicine(self):
        today = timezone.localdate()

        values = {
            "medicine": self.medicine,
            "batch_number": "BATCH-001",
            "supplier_name": "Test Supplier",
            "received_date": today,
            "expiry_date": today + timedelta(days=30),
            "purchase_price": "2.00",
        }

        Batch.objects.create(**values)

        with self.assertRaises(ValidationError):
            Batch(**values).full_clean()