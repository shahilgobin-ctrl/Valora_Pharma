"""Manager, shop, and pharmacist operate on one physical inventory."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from accounts.access import role_home_name
from inventory.models import Batch as PhysicalBatch, Medicine
from orders.models import Order, Payment
from orders.services import advance_order, save_allocations
from shop.models import Cart, CartItem
from .forms import BatchForm
from .models import Batch, PurchaseOrder, PurchaseOrderLine, Supplier
from .selectors import risks
from .services import receive_order, save_batch


class SharedManagerInventoryTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user("manager@example.test", "Test-pass-42", account_type="staff")
        self.manager.groups.add(Group.objects.get(name="Pharmacy Managers"))
        self.pharmacist = User.objects.create_user("pharmacist@example.test", "Test-pass-42", account_type="staff")
        self.pharmacist.groups.add(Group.objects.create(name="Pharmacist"))
        self.customer = User.objects.create_user("customer@example.test", "Test-pass-42")
        self.medicine = Medicine.objects.create(name="Integrated medicine", strength="20 mg",
            dosage_form="Tablet", selling_unit="tablet", selling_price=Decimal("7.50"),
            category_name="Test")
        self.product = self.medicine.storefront
        self.supplier = Supplier.objects.create(name="Exact supplier")
        self.today = timezone.localdate()

    def test_manager_batch_receipt_is_shared_with_shop_and_pharmacist(self):
        form = BatchForm(data={"product": self.product.pk, "supplier": self.supplier.pk,
            "number": "RECEIPT-1", "quantity": 8, "purchase_price": "2.00",
            "received_date": self.today, "expiry_date": self.today + timedelta(days=40),
            "stock_source": "receipt"})
        self.assertTrue(form.is_valid(), form.errors)
        managed = save_batch(form, self.manager)
        physical = PhysicalBatch.objects.get(pk=managed.inventory_batch_id)
        self.assertEqual((physical.medicine_id, physical.quantity_available), (self.medicine.pk, 8))
        self.assertEqual(self.product.available_stock, 8)
        self.client.force_login(self.pharmacist)
        self.assertContains(self.client.get(reverse("pharmacist:inventory")), "Integrated medicine")

    def test_purchase_receipt_and_completion_use_same_batch_and_payment(self):
        purchase = PurchaseOrder.objects.create(supplier=self.supplier, ordered_date=self.today,
            expected_date=self.today + timedelta(days=2), created_by=self.manager)
        line = PurchaseOrderLine.objects.create(order=purchase, product=self.product,
            quantity=5, unit_cost=Decimal("2.00"))
        receive_order(purchase.pk, [{"line_id": line.pk, "expected_received": 0,
            "quantity": 5, "batch_number": "PO-RECEIPT", "received_date": self.today,
            "expiry_date": self.today + timedelta(days=40)}], self.manager)
        managed = Batch.objects.get(number="PO-RECEIPT")
        physical = managed.inventory_batch
        self.assertEqual(self.product.available_stock, 5)
        CartItem.objects.create(cart=Cart.objects.create(user=self.customer), product=self.product, quantity=2)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(reverse("shop:api_checkout"), {"delivery_method": "pickup"}).status_code, 201)
        order = Order.objects.get(customer=self.customer)
        payment_pk = Payment.objects.get(order=order).pk
        save_allocations(order.pk, [{"item": order.items.get(), "batch": physical, "quantity": 2}], self.pharmacist)
        for status in ["confirmed", "preparing", "ready"]:
            advance_order(order.pk, status, self.pharmacist)
        self.client.force_login(self.pharmacist)
        self.assertEqual(self.client.post(reverse("pharmacist:order_record", args=[order.pk]),
            {"action": "complete"}).status_code, 302)
        physical.refresh_from_db(); managed.refresh_from_db()
        self.assertEqual((physical.quantity_available, managed.quantity, self.product.available_stock), (3, 3, 3))
        self.assertEqual(Payment.objects.get(order=order).pk, payment_pk)

    def test_expiry_and_roles_remain_consistent(self):
        PhysicalBatch.objects.create(medicine=self.medicine, batch_number="EXPIRED",
            supplier_name=self.supplier.name, received_date=self.today - timedelta(days=20),
            expiry_date=self.today - timedelta(days=1), quantity_available=9, purchase_price=2)
        self.assertEqual(self.product.available_stock, 0)
        self.assertEqual(risks()["expired"].count(), 1)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("manager:dashboard")).status_code, 403)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("manager:dashboard")).status_code, 200)
        self.assertEqual(role_home_name(self.manager), "manager:dashboard")
        self.client.force_login(self.pharmacist)
        self.assertEqual(self.client.get(reverse("manager:dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("pharmacist:dashboard")).status_code, 200)
