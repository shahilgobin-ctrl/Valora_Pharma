from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from .models import Prescription


class PrescriptionValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()

        cls.customer = user_model.objects.create_user(
            email="customer@example.com",
            account_type="customer",
        )
        cls.pharmacist = user_model.objects.create_user(
            email="pharmacist@example.com",
            account_type="staff",
        )

    def make_prescription(self, **changes):
        values = {
            "customer": self.customer,
            "document": SimpleUploadedFile(
                "sample.pdf",
                b"%PDF-1.4\nvalidation-test",
                content_type="application/pdf",
            ),
        }
        values.update(changes)
        return Prescription(**values)

    def test_pending_prescription_is_valid(self):
        self.make_prescription().full_clean()

    def test_staff_cannot_be_prescription_customer(self):
        prescription = self.make_prescription(
            customer=self.pharmacist
        )

        with self.assertRaises(ValidationError) as error:
            prescription.full_clean()

        self.assertIn("customer", error.exception.message_dict)

    def test_rejection_requires_nonblank_reason(self):
        prescription = self.make_prescription(
            status=Prescription.Status.REJECTED,
            reviewed_by=self.pharmacist,
            reviewed_at=timezone.now(),
            rejection_reason="   ",
        )
        prescription.uploaded_at = prescription.reviewed_at

        with self.assertRaises(ValidationError) as error:
            prescription.full_clean()

        self.assertIn(
            "rejection_reason",
            error.exception.message_dict,
        )

    def test_approval_requires_review_metadata(self):
        prescription = self.make_prescription(
            status=Prescription.Status.APPROVED
        )

        with self.assertRaises(ValidationError) as error:
            prescription.full_clean()

        self.assertIn("reviewed_by", error.exception.message_dict)
        self.assertIn("reviewed_at", error.exception.message_dict)