"""Retain the shop branch's simulated payment contract on shared orders."""
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from orders.models import Order, Payment
from .models import Cart, CartItem, Category, ShopSettings
from .tests import make_product


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CheckoutPaymentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("shop-customer@example.test", "Test-pass-42")
        self.product = make_product(name="Test medicine", price=250, stock_quantity=2,
                                    category=Category.objects.create(name="Test category"))
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        ShopSettings.objects.filter(pk=1).update(delivery_fee=100)
        self.client.force_login(self.user)

    def test_checkout_records_a_successful_demo_payment(self):
        response = self.client.post(reverse("shop:api_checkout"))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["payment_status"], "succeeded")
        order = Order.objects.get(customer=self.user)
        payment = Payment.objects.get(order=order)
        self.assertTrue(payment.is_simulated_online)
        self.assertIsNone(payment.refunded_at)
        self.assertEqual(payment.amount, Decimal("350"))
        self.assertIsNotNone(payment.recorded_at)
        self.assertEqual(order.delivery_method, "delivery")
        self.assertEqual(order.total_amount, Decimal("350"))
        self.assertEqual(self.product.medicine.batches.get().quantity_available, 2)

    def test_pickup_has_no_fee_in_page_and_checkout(self):
        page = self.client.get(reverse("shop:cart"), {"delivery_method": "pickup"})
        self.assertEqual(page.context["delivery"], 0)
        self.assertEqual(page.context["total"], Decimal("250"))
        self.assertContains(page, 'name="delivery_method" value="pickup" checked')
        self.assertContains(page, "successful payment")
        response = self.client.post(reverse("shop:api_checkout"), {"delivery_method": "pickup", "total": "1"})
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(customer=self.user)
        self.assertEqual(order.delivery_fee, 0)
        self.assertEqual(order.total_amount, Decimal("250"))
        self.assertEqual(order.payment.amount, Decimal("250"))

    def test_invalid_delivery_method_cannot_place_order(self):
        response = self.client.post(reverse("shop:api_checkout"), {"delivery_method": "invalid"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.exists())
        self.assertTrue(CartItem.objects.filter(cart__user=self.user).exists())

    def test_updated_photographs_are_available_without_overwriting_custom_artwork(self):
        from django.contrib.staticfiles import finders
        self.product.medicine.name = "Paracetamol"
        self.product.medicine.save()
        self.assertTrue(finders.find("shop/products/paracetamol.jpg"))
        self.assertEqual(self.product.image_url, "/static/shop/products/paracetamol.jpg")
        self.product.image = "home/photos/paracetamol-home.jpg"
        self.assertEqual(self.product.image_url, "/static/home/photos/paracetamol-home.jpg")
