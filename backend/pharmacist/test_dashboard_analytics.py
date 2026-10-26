"""Dashboard counters and seven-day activity using an empty and populated test database."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import Batch, Medicine
from orders.models import Order


class DashboardAnalyticsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        staff = get_user_model().objects.create_user(
            email="dashboard-staff@example.invalid", account_type="staff"
        )
        staff.groups.add(Group.objects.get_or_create(name="Pharmacist")[0])
        cls.staff = staff

    def setUp(self):
        self.client.force_login(self.staff)

    def test_empty_database_has_real_zero_values_and_seven_days(self):
        response = self.client.get(reverse("pharmacist:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pending_prescriptions"], 0)
        self.assertEqual(response.context["open_orders"], 0)
        self.assertEqual(response.context["revenue_today"], 0)
        self.assertEqual(response.context["low_stock_count"], 0)
        self.assertEqual(len(response.context["activity"]), 7)
        self.assertFalse(response.context["activity_has_data"])
        self.assertContains(response, "No transactions in the last seven days")

    def test_low_stock_and_expiring_batches_ignore_expired_inventory(self):
        medicine = Medicine.objects.create(
            name="Example medicine", strength="10 mg", dosage_form="tablet",
            selling_unit="tablet", selling_price=Decimal("15.00"),
            reorder_level=10,
        )
        Batch.objects.create(
            medicine=medicine, batch_number="CURRENT-A",
            supplier_name="Example Supplier", received_date=timezone.localdate()-timedelta(days=20),
            expiry_date=timezone.localdate()+timedelta(days=20),
            quantity_available=4, purchase_price=Decimal("5.00"),
        )
        Batch.objects.create(
            medicine=medicine, batch_number="EXPIRED-B",
            supplier_name="Example Supplier", received_date=timezone.localdate()-timedelta(days=100),
            expiry_date=timezone.localdate()-timedelta(days=1),
            quantity_available=50, purchase_price=Decimal("5.00"),
        )
        response = self.client.get(reverse("pharmacist:dashboard"))
        self.assertEqual(response.context["low_stock_count"], 1)
        self.assertEqual(response.context["expiring_batches_count"], 1)
        self.assertEqual(response.context["out_of_stock_count"], 0)
        self.assertContains(response, "Example medicine")

    def test_new_order_chart_uses_actual_created_date(self):
        customer = get_user_model().objects.create_user(
            email="dashboard-customer@example.invalid", account_type="customer"
        )
        Order.objects.create(kind=Order.Kind.ONLINE, customer=customer,
                             contact_name="A customer")
        response = self.client.get(reverse("pharmacist:dashboard"))
        self.assertEqual(response.context["open_orders"], 1)
        self.assertEqual(response.context["activity_new_total"], 1)
        self.assertTrue(response.context["activity_has_data"])
        self.assertEqual(response.context["activity"][-1]["new"], 1)
