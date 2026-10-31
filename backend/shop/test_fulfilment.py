"""Customer checkout and pharmacist fulfilment share medicine, stock and payment."""
from datetime import timedelta
from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from inventory.models import Batch, Medicine
from orders.models import Order, Payment, StockMovement
from orders.services import advance_order, cancel_order, complete_order, save_allocations
from prescriptions.models import Prescription
from .models import Cart, CartItem, Order as LegacyOrder


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SharedFulfilmentTests(TestCase):
    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.customer = User.objects.create_user("customer@example.test", "Test-pass-42")
        self.pharmacist = User.objects.create_user("staff@example.test", "Test-pass-42", account_type="staff")
        self.pharmacist.groups.add(Group.objects.get_or_create(name="Pharmacist")[0])
        self.medicine = Medicine.objects.create(name="Test medicine", strength="500 mg", dosage_form="Tablet",
            selling_unit="tablet", selling_price=Decimal("3.50"), category_name="Pain relief")
        self.product = self.medicine.storefront
        self.batch = Batch.objects.create(medicine=self.medicine, batch_number="usable", supplier_name="Test",
            expiry_date=timezone.localdate()+timedelta(days=20), quantity_available=10, purchase_price=1)
        self.cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(cart=self.cart, product=self.product, quantity=2)
        self.client.force_login(self.customer)

    def checkout(self, **data):
        return self.client.post(reverse("shop:api_checkout"), {"delivery_method": "pickup", **data})

    def ready_order(self, order):
        save_allocations(order.pk, [{"item": order.items.get(), "batch": self.batch, "quantity": 2}], self.pharmacist)
        for status in ["confirmed", "preparing", "ready"]:
            advance_order(order.pk, status, self.pharmacist)

    def test_checkout_and_completion_record_payment_once_and_stock_once(self):
        self.assertEqual(self.checkout().status_code, 201)
        order = Order.objects.get(customer=self.customer)
        self.assertEqual(order.total_amount, Decimal("7.00"))
        self.assertEqual(order.items.get().medicine_id, self.medicine.pk)
        self.assertFalse(LegacyOrder.objects.exists())
        payment = Payment.objects.get(order=order)
        self.assertTrue(payment.is_simulated_online)
        self.assertEqual(payment.recorded_by_id, self.customer.pk)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_available, 10)
        self.assertEqual(self.checkout().status_code, 409)
        self.ready_order(order)
        self.client.force_login(self.pharmacist)
        response = self.client.post(reverse("pharmacist:order_record", args=[order.pk]), {"action": "complete"})
        self.assertRedirects(response, reverse("pharmacist:receipt", args=[order.pk]))
        complete_order(order.pk, "cash", None, self.pharmacist)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_available, 8)
        self.assertEqual(Payment.objects.get(order=order).pk, payment.pk)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_inventory_updates_drive_home_shop_and_json_without_metadata_edits(self):
        self.medicine.name = "Updated inventory medicine"
        self.medicine.selling_price = Decimal("4.25")
        self.medicine.save()
        for route in ["home", "shop:shop"]:
            response = self.client.get(reverse(route))
            self.assertContains(response, "Updated inventory medicine")
            self.assertContains(response, "4.25")
        data = self.client.get(reverse("shop:api_product", args=[self.product.slug])).json()
        self.assertEqual(Decimal(data["price"]), Decimal("4.25"))
        self.assertEqual(data["stock_quantity"], 10)

    def test_expired_batches_cannot_supply_checkout(self):
        self.batch.received_date = timezone.localdate()-timedelta(days=10)
        self.batch.expiry_date = timezone.localdate()
        self.batch.save()
        self.assertEqual(self.checkout().status_code, 409)
        self.assertFalse(Order.objects.exists())
        self.assertTrue(self.cart.items.exists())

    def test_pending_orders_reduce_available_stock_and_cancel_releases_it(self):
        self.assertEqual(self.checkout().status_code, 201)
        self.assertEqual(self.product.available_stock, 8)
        order = Order.objects.get()
        cancel_order(order.pk, "Customer request", self.pharmacist)
        self.assertIsNotNone(Payment.objects.get(order=order).refunded_at)
        self.assertEqual(self.product.available_stock, 10)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_available, 10)

    def test_prescription_enters_existing_review_queue(self):
        self.medicine.prescription_required = True
        self.medicine.save()
        self.assertEqual(self.checkout().status_code, 409)
        upload = SimpleUploadedFile("private.pdf", b"%PDF-1.4\nTest", content_type="application/pdf")
        self.assertEqual(self.checkout(prescription=upload).status_code, 201)
        order = Order.objects.get()
        prescription = Prescription.objects.get(customer=self.customer)
        self.assertEqual(order.prescription_id, prescription.pk)
        self.assertEqual(prescription.status, Prescription.Status.PENDING)
        self.client.force_login(self.pharmacist)
        self.assertContains(self.client.get(reverse("pharmacist:prescription_queue")), self.customer.email)
        self.assertEqual(self.client.post(reverse("pharmacist:order_record", args=[order.pk]),
            {"action": "advance", "target": "confirmed"}).status_code, 400)

    def test_non_customer_cannot_mutate_cart_or_checkout(self):
        self.client.force_login(self.pharmacist)
        for name in ["api_cart_add", "api_cart_remove", "api_cart_update", "api_checkout"]:
            self.assertEqual(self.client.post(reverse("shop:"+name), {}, content_type="application/json").status_code, 403)
        self.assertFalse(Order.objects.exists())

    def test_archived_medicine_cannot_be_checked_out(self):
        self.medicine.is_active = False
        self.medicine.save()
        self.assertEqual(self.checkout().status_code, 409)
        self.assertFalse(Order.objects.exists())

    def test_payment_failure_rolls_back_order_and_keeps_cart(self):
        with patch("orders.services.Payment.save", side_effect=RuntimeError("simulated failure")):
            with self.assertRaises(RuntimeError):
                self.checkout()
        self.assertFalse(Order.objects.exists())
        self.assertTrue(self.cart.items.exists())
