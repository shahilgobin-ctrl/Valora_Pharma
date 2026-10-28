from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import Cart, CartItem, Category, Order, Product, ShopSettings


class CatalogueDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Original category", slug="original-category")
        cls.product = Product.objects.create(name="Original medicine", slug="paracetamol",
            price=219, stock_quantity=10, category=cls.category,
            image="/static/shop/products/paracetamol.svg", description="Original description")
        cls.user = get_user_model().objects.create_user(email="catalogue@example.test", password="TestPass123!")

    def test_database_edits_appear_in_home_shop_detail_and_api(self):
        self.category.name = "Updated category"
        self.category.save()
        self.product.name = "Updated medicine"
        self.product.price = 777
        self.product.description = "Updated description"
        self.product.stock_quantity = 0
        self.product.image = "shop/products/vitamin-c.svg"
        self.product.save()
        for name, args in [("home", []), ("shop:shop", []), ("shop:product", [self.product.slug])]:
            response = self.client.get(reverse(name, args=args))
            self.assertContains(response, "Updated medicine")
            self.assertContains(response, "Rs 777")
            self.assertContains(response, "/static/shop/products/vitamin-c.svg")
        home = self.client.get(reverse("home"))
        self.assertContains(home, "Updated category")
        self.assertContains(home, "Out of stock")
        data = self.client.get(reverse("shop:api_product", args=[self.product.slug])).json()
        self.assertEqual(data["name"], "Updated medicine")
        self.assertEqual(data["price"], 777)
        self.assertEqual(data["stock_quantity"], 0)
        self.assertEqual(data["image"], "/static/shop/products/vitamin-c.svg")

    def test_new_database_product_appears_without_code_changes(self):
        product = Product.objects.create(name="New database medicine", slug="new-database-medicine",
            price=123, category=self.category, stock_quantity=1)
        self.assertContains(self.client.get(reverse("home")), product.name)
        self.assertContains(self.client.get(reverse("shop:shop")), product.name)

    def test_empty_image_uses_same_fallback_everywhere(self):
        self.product.image = ""
        self.product.save()
        for name, args in [("home", []), ("shop:shop", []), ("shop:product", [self.product.slug])]:
            self.assertContains(self.client.get(reverse(name, args=args)), "/static/shop/products/medicine.svg")
        data = self.client.get(reverse("shop:api_product", args=[self.product.slug])).json()
        self.assertEqual(data["image"], "/static/shop/products/medicine.svg")

    def test_admin_delivery_charge_is_used_by_cart_and_checkout(self):
        settings = ShopSettings.objects.get(pk=1)
        settings.delivery_fee = 37
        settings.save()
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=2)
        self.client.force_login(self.user)
        api = self.client.get(reverse("shop:api_cart")).json()
        self.assertEqual((api["subtotal"], api["delivery"], api["total"]), (438, 37, 475))
        page = self.client.get(reverse("shop:cart"))
        self.assertEqual((page.context["subtotal"], page.context["delivery"], page.context["total"]), (438, 37, 475))
        self.assertEqual(page.context["cart_count"], 2)
        # Client-supplied money is ignored; the backend recalculates from records.
        response = self.client.post(reverse("shop:api_checkout"),
            {"price": 1, "total": 1, "delivery": 0}, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.total, 475)
        self.assertEqual(order.items.get().unit_price, 219)
        self.product.price = 999
        self.product.save()
        order.refresh_from_db()
        self.assertEqual(order.total, 475)
        self.assertEqual(order.items.get().unit_price, 219)

    def test_empty_cart_has_no_delivery_charge(self):
        self.client.force_login(self.user)
        data = self.client.get(reverse("shop:api_cart")).json()
        self.assertEqual((data["subtotal"], data["delivery"], data["total"]), (0, 0, 0))

    def test_sample_import_preserves_existing_edits(self):
        self.product.price = 888
        self.product.image = "shop/products/vitamin-c.svg"
        self.product.save()
        call_command("seed_shop", stdout=StringIO())
        self.product.refresh_from_db()
        self.assertEqual(self.product.price, 888)
        self.assertEqual(self.product.image, "shop/products/vitamin-c.svg")
        self.assertEqual(self.product.name, "Original medicine")
