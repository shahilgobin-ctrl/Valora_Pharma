"""Walk-in POS checkout integration tests."""
from datetime import timedelta
from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from inventory.models import Batch, Medicine
from orders.models import Order, Payment, StockMovement
from orders.services import checkout_walk_in, create_order
from prescriptions.models import Prescription


class WalkInPOSTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        media = override_settings(MEDIA_ROOT=directory.name)
        media.enable()
        self.addCleanup(media.disable)
        users = get_user_model()
        self.staff = users.objects.create_user(email="pos@example.invalid", account_type="staff")
        group, _ = Group.objects.get_or_create(name="Pharmacist")
        self.staff.groups.add(group)
        self.customer = users.objects.create_user(email="buyer@example.invalid", account_type="customer")
        self.medicine = Medicine.objects.create(
            name="POS medicine", strength="500 mg", dosage_form="Tablet",
            selling_unit="tablet", selling_price=Decimal("2.50"),
        )
        self.early = self.batch("EARLY", 3, 30)
        self.late = self.batch("LATE", 10, 90)
        self.client.force_login(self.staff)

    def batch(self, number, quantity, days):
        return Batch.objects.create(
            medicine=self.medicine, batch_number=number, supplier_name="Test supplier",
            quantity_available=quantity, purchase_price=1,
            received_date=timezone.localdate() - timedelta(days=60),
            expiry_date=timezone.localdate() + timedelta(days=days),
        )

    def checkout(self, **changes):
        values = dict(user=self.staff, lines=[{"medicine":self.medicine,"quantity":5}],
                      method="cash", cash_tendered=Decimal("20.00"), submission_key=uuid4())
        values.update(changes)
        return checkout_walk_in(**values)

    def payload(self, action="checkout"):
        response = self.client.get(reverse("pharmacist:sale_form"))
        return {
            "submission_key":str(response.context["form"].initial["submission_key"]),
            "lines-TOTAL_FORMS":"1","lines-INITIAL_FORMS":"0",
            "lines-MIN_NUM_FORMS":"0","lines-MAX_NUM_FORMS":"50",
            "lines-0-medicine":str(self.medicine.pk),"lines-0-quantity":"5",
            "method":"cash","cash_tendered":"20.00","action":action,
        }

    def prescription(self, status="approved"):
        rx = Prescription(customer=self.customer, status=status)
        if status != "pending":
            rx.reviewed_by = self.staff
            rx.reviewed_at = timezone.now()
        if status == "rejected":
            rx.rejection_reason = "Unreadable"
        rx.document.save("sample.pdf", ContentFile(b"%PDF-1.4 test"), save=False)
        rx.full_clean()
        rx.save()
        return rx

    def test_cash_checkout_splits_earliest_expiry_first(self):
        order = self.checkout()
        self.early.refresh_from_db()
        self.late.refresh_from_db()
        self.assertEqual((self.early.quantity_available,self.late.quantity_available),(0,8))
        self.assertEqual(order.status,"completed")
        self.assertEqual(order.payment.amount,Decimal("12.50"))
        self.assertEqual(order.payment.change,Decimal("7.50"))
        self.assertEqual(StockMovement.objects.count(),2)
        self.assertEqual(order.items.get().selling_unit,"tablet")

    def test_expired_today_and_empty_batches_are_not_used(self):
        expired=self.batch("EXPIRED",50,-1)
        today=self.batch("TODAY",50,0)
        empty=self.batch("EMPTY",0,10)
        order=self.checkout()
        self.assertFalse(order.items.get().allocations.filter(batch__in=[expired,today,empty]).exists())

    def test_shortage_rolls_back_every_record(self):
        with self.assertRaises(ValidationError):
            self.checkout(lines=[{"medicine":self.medicine,"quantity":14}])
        self.assertEqual(Order.objects.count(),0)
        self.assertEqual(Payment.objects.count(),0)
        self.assertEqual(StockMovement.objects.count(),0)
        self.early.refresh_from_db()
        self.assertEqual(self.early.quantity_available,3)

    def test_insufficient_cash_rolls_back(self):
        with self.assertRaises(ValidationError):
            self.checkout(cash_tendered=Decimal("1.00"))
        self.assertFalse(Order.objects.exists())

    def test_completion_failure_rolls_back_allocations_and_stock(self):
        with patch("orders.services.complete_order",side_effect=ValidationError("Stock changed")):
            with self.assertRaises(ValidationError):
                self.checkout()
        self.assertFalse(Order.objects.exists())
        self.early.refresh_from_db()
        self.assertEqual(self.early.quantity_available,3)

    def test_repeated_checkout_does_not_charge_or_deduct_twice(self):
        key=uuid4()
        first=self.checkout(submission_key=key)
        second=self.checkout(submission_key=key)
        self.assertEqual(first.pk,second.pk)
        self.assertEqual(Payment.objects.count(),1)
        self.late.refresh_from_db()
        self.assertEqual(self.late.quantity_available,8)

    def test_draft_submission_replay_does_not_complete_draft(self):
        key=uuid4()
        draft=create_order(user=self.staff,kind="walk_in",lines=[{"medicine":self.medicine,"quantity":1}],submission_key=key)
        result=self.checkout(submission_key=key)
        self.assertEqual(result.pk,draft.pk)
        self.assertEqual(result.status,"pending")
        self.assertFalse(Payment.objects.exists())

    def test_card_checkout_has_no_cash_tendered(self):
        order=self.checkout(method="card",cash_tendered=Decimal("99.00"))
        self.assertIsNone(order.payment.cash_tendered)

    def test_prescription_medicine_requires_approved_document_and_owner(self):
        self.medicine.prescription_required=True
        self.medicine.save()
        with self.assertRaises(ValidationError):
            self.checkout()
        rx=self.prescription()
        order=self.checkout(customer=self.customer,prescription=rx)
        self.assertEqual(order.prescription_id,rx.pk)

    def test_rejected_prescription_cannot_checkout(self):
        with self.assertRaises(ValidationError):
            self.checkout(customer=self.customer,prescription=self.prescription("rejected"))
        self.assertFalse(Order.objects.exists())

    def test_checkout_post_uses_catalogue_prices_and_redirects_to_receipt(self):
        data=self.payload()
        data["total_amount"]="0.01"
        data["lines-0-unit_price"]="0.01"
        response=self.client.post(reverse("pharmacist:sale_form"),data)
        order=Order.objects.get()
        self.assertRedirects(response,reverse("pharmacist:receipt",args=[order.pk]))
        self.assertEqual(order.total_amount,Decimal("12.50"))
        repeated=self.client.post(reverse("pharmacist:sale_form"),data)
        self.assertEqual(repeated.status_code,302)
        self.assertEqual(Payment.objects.count(),1)

    def test_draft_without_payment_and_invalid_token(self):
        data=self.payload("draft")
        data.pop("cash_tendered")
        response=self.client.post(reverse("pharmacist:sale_form"),data)
        self.assertEqual(response.status_code,302)
        self.assertEqual(Order.objects.get().status,"pending")
        self.assertFalse(Payment.objects.exists())
        data["submission_key"]=str(uuid4())
        self.assertEqual(self.client.post(reverse("pharmacist:sale_form"),data).status_code,400)
        self.assertEqual(Order.objects.count(),1)

    def test_catalogue_stock_excludes_expired_and_archived_products(self):
        self.batch("OLD",100,-1)
        archived=Medicine.objects.create(name="Archived",strength="1 mg",dosage_form="Tablet",selling_price=1,is_active=False)
        response=self.client.get(reverse("pharmacist:sale_form"))
        catalogue=response.context["catalogue"]
        self.assertEqual(next(p["stock"] for p in catalogue if p["id"]==self.medicine.pk),13)
        self.assertNotIn(archived.pk,[p["id"] for p in catalogue])
        self.assertContains(response,'id="pos-products"')

    def test_invalid_payment_and_invalid_action_create_no_order(self):
        data=self.payload()
        data["cash_tendered"]=""
        self.assertEqual(self.client.post(reverse("pharmacist:sale_form"),data).status_code,400)
        data["action"]="invalid"
        self.assertEqual(self.client.post(reverse("pharmacist:sale_form"),data).status_code,400)
        self.assertFalse(Order.objects.exists())

