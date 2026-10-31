from datetime import timedelta
from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from inventory.models import Batch, Medicine
from prescriptions.models import Prescription
from .models import Allocation, Order, Payment, StockMovement
from .services import advance_order, complete_order, create_order, save_allocations


class OrderWorkflowTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = override_settings(MEDIA_ROOT=directory.name)
        settings.enable()
        self.addCleanup(settings.disable)
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            email="workflow@example.com", account_type="staff"
        )
        group, _ = Group.objects.get_or_create(name="Pharmacist")
        self.staff.groups.add(group)
        self.customer = user_model.objects.create_user(email="customer@example.com")
        self.medicine = Medicine.objects.create(
            name="Demo medicine",
            strength="500 mg",
            dosage_form="Tablet",
            selling_price=Decimal("2.50"),
        )
        self.batch = Batch.objects.create(
            medicine=self.medicine,
            batch_number="B1",
            supplier_name="Demo supplier",
            quantity_available=20,
            purchase_price=1,
            expiry_date=timezone.localdate() + timedelta(days=60),
        )
        self.client.force_login(self.staff)

    def create(self, **kwargs):
        return create_order(
            user=self.staff,
            kind=kwargs.pop("kind", "walk_in"),
            lines=kwargs.pop("lines", [{"medicine": self.medicine, "quantity": 4}]),
            **kwargs,
        )

    def allocate(self, order, quantity=4, batch=None):
        return save_allocations(
            order.pk,
            [
                {
                    "item": order.items.get(),
                    "batch": batch or self.batch,
                    "quantity": quantity,
                }
            ],
            self.staff,
        )

    def complete(self, order, **kwargs):
        return complete_order(
            order.pk,
            kwargs.get("method", "cash"),
            kwargs.get("cash_tendered", Decimal("20.00")),
            self.staff,
        )

    def prescription(self, status="approved", customer=None):
        record = Prescription(customer=customer or self.customer, status=status)
        if status != "pending":
            record.reviewed_by = self.staff
            record.reviewed_at = timezone.now()
        if status == "rejected":
            record.rejection_reason = "Unreadable"
        record.document.save("test.pdf", ContentFile(b"%PDF-1.4 test"), save=False)
        record.full_clean()
        record.save()
        return record

    def test_cash_sale_completes_stock_payment_and_receipt(self):
        order = self.create()
        self.allocate(order)
        self.complete(order)
        self.batch.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.batch.quantity_available, 16)
        self.assertEqual(order.status, "completed")
        self.assertEqual(order.payment.amount, Decimal("10.00"))
        self.assertEqual(order.payment.change, Decimal("10.00"))
        self.assertEqual(StockMovement.objects.count(), 1)
        response = self.client.get(reverse("pharmacist:receipt", args=[order.pk]))
        self.assertContains(response, "Demo medicine")
        self.assertContains(response, "10.00")

    def test_completion_replay_does_not_charge_or_deduct_twice(self):
        order = self.create()
        self.allocate(order)
        self.complete(order)
        self.complete(order)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_available, 16)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_prices_and_names_are_snapshots(self):
        order = self.create()
        Medicine.objects.filter(pk=self.medicine.pk).update(
            name="Renamed", selling_price=99
        )
        self.allocate(order)
        self.complete(order)
        order.refresh_from_db()
        self.assertEqual(order.total_amount, Decimal("10.00"))
        self.assertIn("Demo medicine", order.items.get().medicine_name)

    def test_insufficient_cash_rolls_back(self):
        order = self.create()
        self.allocate(order)
        with self.assertRaises(ValidationError):
            self.complete(order, cash_tendered=Decimal("1.00"))
        self.batch.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.batch.quantity_available, 20)
        self.assertEqual(order.status, "pending")
        self.assertFalse(Payment.objects.exists())

    def test_failure_during_deduction_rolls_back_everything(self):
        order = self.create()
        self.allocate(order)
        with patch(
            "orders.services.StockMovement.objects.create",
            side_effect=ValidationError("Failure"),
        ):
            with self.assertRaises(ValidationError):
                self.complete(order)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_available, 20)
        self.assertFalse(Payment.objects.exists())

    def test_card_payment_is_simulated_without_cash(self):
        order = self.create()
        self.allocate(order)
        self.complete(order, method="card", cash_tendered=None)
        self.assertIsNone(Payment.objects.get().cash_tendered)

    def test_no_allocation_blocks_completion(self):
        with self.assertRaises(ValidationError):
            self.complete(self.create())

    def test_allocation_must_match_quantity(self):
        with self.assertRaises(ValidationError):
            self.allocate(self.create(), quantity=3)
        self.assertFalse(Allocation.objects.exists())

    def test_wrong_medicine_batch_rejected(self):
        other = Medicine.objects.create(
            name="Other", strength="1 mg", dosage_form="Tablet", selling_price=1
        )
        self.batch.medicine = other
        self.batch.save()
        with self.assertRaises(ValidationError):
            self.allocate(self.create())

    def test_expired_and_expiring_today_batches_rejected(self):
        order = self.create()
        for days in (0, -1):
            Batch.objects.filter(pk=self.batch.pk).update(
                received_date=timezone.localdate() - timedelta(days=30),
                expiry_date=timezone.localdate() + timedelta(days=days),
            )
            with self.assertRaises(ValidationError):
                self.allocate(order)

    def test_stock_rechecked_after_allocating(self):
        order = self.create()
        self.allocate(order)
        Batch.objects.filter(pk=self.batch.pk).update(quantity_available=2)
        with self.assertRaises(ValidationError):
            self.complete(order)
        self.assertFalse(Payment.objects.exists())

    def test_two_orders_cannot_oversell_same_batch(self):
        Batch.objects.filter(pk=self.batch.pk).update(quantity_available=4)
        first, second = self.create(), self.create()
        self.allocate(first)
        self.allocate(second)
        self.complete(first)
        with self.assertRaises(ValidationError):
            self.complete(second)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_available, 0)
        self.assertEqual(Payment.objects.count(), 1)

    def test_split_batch_allocation(self):
        second = Batch.objects.create(
            medicine=self.medicine,
            batch_number="B2",
            supplier_name="Demo",
            quantity_available=2,
            purchase_price=1,
            expiry_date=timezone.localdate() + timedelta(days=40),
        )
        order = self.create()
        save_allocations(
            order.pk,
            [
                {"item": order.items.get(), "batch": self.batch, "quantity": 2},
                {"item": order.items.get(), "batch": second, "quantity": 2},
            ],
            self.staff,
        )
        self.complete(order)
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_archived_medicine_cannot_be_sold(self):
        Medicine.objects.filter(pk=self.medicine.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            self.create()
        self.assertFalse(Order.objects.exists())

    def test_duplicate_medicines_rollback_draft(self):
        with self.assertRaises(ValidationError):
            self.create(lines=[{"medicine": self.medicine, "quantity": 1}] * 2)
        self.assertFalse(Order.objects.exists())

    def test_creation_token_returns_original_order(self):
        key = uuid4()
        first = self.create(submission_key=key)
        second = self.create(submission_key=key)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Order.objects.count(), 1)

    def test_prescription_medicine_requires_approval_and_owner(self):
        Medicine.objects.filter(pk=self.medicine.pk).update(prescription_required=True)
        with self.assertRaises(ValidationError):
            self.create()
        for status in ("pending", "rejected"):
            with self.assertRaises(ValidationError):
                self.create(
                    customer=self.customer, prescription=self.prescription(status)
                )
        approved = self.prescription()
        with self.assertRaises(ValidationError):
            self.create(prescription=approved)
        order = self.create(customer=self.customer, prescription=approved)
        self.allocate(order)
        self.complete(order)
        self.assertEqual(Payment.objects.count(), 1)

    def test_prescription_cannot_be_reused_for_another_order(self):
        record = self.prescription()
        self.create(customer=self.customer, prescription=record)
        with self.assertRaises(ValidationError):
            self.create(customer=self.customer, prescription=record)

    def test_online_status_sequence(self):
        order = self.create(kind="online", customer=self.customer)
        with self.assertRaises(ValidationError):
            advance_order(order.pk, "ready", self.staff)
        with self.assertRaises(ValidationError):
            self.complete(order)
        for status in ("confirmed", "preparing"):
            advance_order(order.pk, status, self.staff)
        with self.assertRaises(ValidationError):
            advance_order(order.pk, "ready", self.staff)
        self.allocate(order)
        advance_order(order.pk, "ready", self.staff)
        self.complete(order)
        order.refresh_from_db()
        self.assertEqual(order.status, "completed")

    def test_pending_prescription_blocks_online_confirmation(self):
        order = self.create(
            kind="online",
            customer=self.customer,
            prescription=self.prescription("pending"),
        )
        with self.assertRaises(ValidationError):
            advance_order(order.pk, "confirmed", self.staff)
        response = self.client.get(
            reverse("pharmacist:prescription_detail", args=[order.prescription_id])
        )
        self.assertContains(response, f"ORD-{order.pk}")
        self.assertContains(response, "Demo medicine")

    def test_customer_cannot_call_services(self):
        order = self.create()
        with self.assertRaises(PermissionDenied):
            complete_order(order.pk, "card", None, self.customer)

    def test_private_order_and_receipt_routes(self):
        order = self.create()
        self.allocate(order)
        self.complete(order)
        for name in ("order_record", "receipt"):
            url = reverse(f"pharmacist:{name}", args=[order.pk])
            self.client.logout()
            self.assertEqual(self.client.get(url).status_code, 302)
            self.client.force_login(self.customer)
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_receipt_requires_completion_and_existing_order(self):
        order = self.create()
        self.assertEqual(
            self.client.get(reverse("pharmacist:receipt", args=[order.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("pharmacist:order_record", args=[9999])
            ).status_code,
            404,
        )

    def test_csrf_required_for_mutations(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        order = self.create()
        for url in (
            reverse("pharmacist:sale_form"),
            reverse("pharmacist:order_record", args=[order.pk]),
        ):
            self.assertEqual(client.post(url, {}).status_code, 403)

    def test_sale_post_then_allocation_then_completion(self):
        url = reverse("pharmacist:sale_form")
        response = self.client.get(url)
        token = response.context["form"].initial["submission_key"]
        payload = {
            "submission_key": token,
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-0-medicine": str(self.medicine.pk),
            "lines-0-quantity": "4",
            "unit_price": "0.01",
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.get()
        url = reverse("pharmacist:order_record", args=[order.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(
            url,
            {
                "action": "allocate",
                "allocations-TOTAL_FORMS": "1",
                "allocations-INITIAL_FORMS": "0",
                "allocations-0-item": order.items.get().pk,
                "allocations-0-batch": self.batch.pk,
                "allocations-0-quantity": "4",
            },
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.post(
            url, {"action": "complete", "method": "cash", "cash_tendered": "20"}
        )
        self.assertRedirects(response, reverse("pharmacist:receipt", args=[order.pk]))
        self.assertEqual(Payment.objects.get().amount, Decimal("10.00"))

    def test_forged_sale_token_and_invalid_forms_do_not_save(self):
        response = self.client.post(
            reverse("pharmacist:sale_form"), {"submission_key": uuid4()}
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_order_filters_and_dashboard_totals(self):
        order = self.create()
        self.allocate(order)
        self.complete(order)
        response = self.client.get(
            reverse("pharmacist:order_queue"),
            {"kind": "all", "status": "completed", "q": f"ORD-{order.pk}"},
        )
        self.assertContains(response, f"ORD-{order.pk}")
        response = self.client.get(reverse("pharmacist:dashboard"))
        self.assertEqual(response.context["sales_today"], 1)
        self.assertEqual(response.context["revenue_today"], Decimal("10.00"))

    def test_completed_allocations_cannot_be_changed(self):
        order = self.create()
        self.allocate(order)
        self.complete(order)
        with self.assertRaises(ValidationError):
            self.allocate(order)
