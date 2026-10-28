from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Cart, CartItem, Category, Payment, Product


class CheckoutPaymentTests(TestCase):
    def test_checkout_records_a_successful_demo_payment(self):
        user = get_user_model().objects.create_user(email="customer@example.com", password="test-pass")
        category = Category.objects.create(name="Test category")
        product = Product.objects.create(
            name="Test medicine",
            price=250,
            stock_quantity=2,
            category=category,
        )
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)
        self.client.force_login(user)

        response = self.client.post("/api/checkout/")

        self.assertEqual(response.status_code, 201)
        payment = Payment.objects.get(order__user=user)
        self.assertEqual(payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(payment.amount_total, 350)
        self.assertEqual(payment.amount_paid, 350)
        self.assertIsNotNone(payment.paid_at)
