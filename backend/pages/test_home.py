from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import Client, TestCase
from django.urls import reverse

from shop.models import Cart, CartItem, Category, Product


class HomeIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Pain & Fever", slug="pain-fever")
        cls.product = Product.objects.create(
            name="Paracetamol", slug="paracetamol", category=cls.category,
            strength="500mg - Tablet", price=45, stock_quantity=10,
            image="/static/shop/products/paracetamol.svg",
        )
        cls.user = get_user_model().objects.create_user(
            email="integration@example.test", password="StrongTestPass123!"
        )

    def test_home_uses_database_products_and_working_named_links(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Paracetamol")
        self.assertContains(response, reverse("shop:product", args=[self.product.slug]))
        for name in ["shop:shop", "shop:cart", "accounts:login", "accounts:register", "pages:about"]:
            self.assertContains(response, reverse(name))
        self.assertNotContains(response, "login.html")
        self.assertNotContains(response, "medicines.html")
        self.assertTrue(finders.find("shop/products/paracetamol.svg"))

    def test_empty_catalogue_and_inactive_products(self):
        self.product.is_active = False
        self.product.save()
        response = self.client.get(reverse("home"))
        self.assertContains(response, "No medicines are available right now.")
        self.assertNotContains(response, "Paracetamol")

    def test_home_cart_and_logout_use_django_session(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=3)
        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'id="cartCount">3</span>')
        self.assertContains(response, 'method="post" action="/logout/"')
        self.assertNotContains(response, '>Sign in</a>')

    def test_catalogue_product_and_cart_routes(self):
        for url in [reverse("shop:shop"), reverse("shop:product", args=[self.product.slug])]:
            self.assertEqual(self.client.get(url).status_code, 200)
        self.assertRedirects(self.client.get(reverse("shop:cart")), "/login/?next=/cart/")
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("shop:cart")).status_code, 200)

    def test_cart_requires_authentication_and_csrf(self):
        self.assertEqual(self.client.post(reverse("shop:api_cart_add"),
            {"product_id": self.product.pk}, content_type="application/json").status_code, 401)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("shop:api_cart_add"),
            {"product_id": self.product.pk}, content_type="application/json").status_code, 403)
        client.get(reverse("home"))
        response = client.post(reverse("shop:api_cart_add"),
            {"product_id": self.product.pk, "quantity": 2}, content_type="application/json",
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["item_count"], 2)
        self.assertEqual(client.get(reverse("home")).context["cart_count"], 2)

    def test_shared_login_uses_role_destination_and_rejects_external_redirect(self):
        payload = {"email": self.user.email, "password": "StrongTestPass123!"}
        for target in ["/cart/", "https://untrusted.example/"]:
            self.assertRedirects(self.client.post(reverse("accounts:login") + "?next=" + target, payload),
                reverse("accounts:customer_landing"))
            self.client.logout()

    def test_category_cards_use_catalogue_images_and_transparent_logo(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, '/static/shop/products/paracetamol.svg', count=2)
        self.assertContains(response, '/static/accounts/assets/pill-login.svg', count=2)
        self.product.image = ""
        self.product.save()
        self.assertContains(self.client.get(reverse("home")), '/static/shop/products/medicine.svg', count=2)

    def test_admin_selected_condition_icon_and_feature_order(self):
        self.category.image = "home/conditions/pain-fever.svg"
        self.category.save()
        self.product.homepage_order = 1
        self.product.save()
        other = Product.objects.create(name="AAA other medicine", slug="other-medicine", price=99,
            stock_quantity=1, category=self.category, homepage_order=10)
        response = self.client.get(reverse("home"))
        self.assertEqual(list(response.context["products"]), [self.product, other])
        self.assertContains(response, '/static/home/conditions/pain-fever.svg')

    def test_homepage_image_override_does_not_change_shop_or_api(self):
        from pages.models import HomepageProductImage
        HomepageProductImage.objects.create(product=self.product, image="home/photos/paracetamol-home.jpg")
        home = self.client.get(reverse("home"))
        self.assertContains(home, "/static/home/photos/paracetamol-home.jpg")
        self.product.refresh_from_db()
        self.assertEqual(self.product.image, "/static/shop/products/paracetamol.svg")
        shop = self.client.get(reverse("shop:shop"))
        self.assertContains(shop, "/static/shop/products/paracetamol.svg")
        self.assertNotContains(shop, "/static/home/photos/paracetamol-home.jpg")
        api = self.client.get(reverse("shop:api_product", args=[self.product.slug])).json()
        self.assertEqual(api["image"], "/static/shop/products/paracetamol.svg")
        self.assertTrue(finders.find("home/photos/paracetamol-home.jpg"))
