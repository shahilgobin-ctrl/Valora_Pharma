"""Navigation and session behaviour across the final three public pages."""
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PublicNavigationTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user("public@example.test", "Test-pass-42")

    def test_all_public_headers_link_home_shop_about_and_cart(self):
        for route in ["home", "shop:shop", "pages:about"]:
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                for destination in ["home", "shop:shop", "pages:about", "shop:cart"]:
                    self.assertContains(response, f'href="{reverse(destination)}"')
                self.assertContains(response, reverse("accounts:login"))
                self.assertContains(response, reverse("accounts:register"))

    def test_authenticated_headers_use_post_logout_and_keep_session_until_submit(self):
        self.client.force_login(self.customer)
        for route in ["home", "shop:shop", "pages:about"]:
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertContains(response, f'method="post" action="{reverse("accounts:logout")}"')
                self.assertNotContains(response, f'href="{reverse("accounts:logout")}"')
                self.assertContains(response, "csrfmiddlewaretoken")
                self.assertEqual(self.client.session["_auth_user_id"], str(self.customer.pk))
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_about_logout_requires_csrf_and_accepts_its_form_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.customer)
        client.get(reverse("pages:about"))
        self.assertEqual(client.post(reverse("accounts:logout")).status_code, 403)
        token = client.cookies["csrftoken"].value
        self.assertRedirects(client.post(reverse("accounts:logout"), {"csrfmiddlewaretoken": token}),
                             reverse("accounts:login"))

    def test_about_does_not_change_pharmacist_dashboard_destination(self):
        pharmacist = User.objects.create_user("public-pharmacist@example.test", "Test-pass-42", account_type="staff")
        pharmacist.groups.add(Group.objects.get_or_create(name="Pharmacist")[0])
        self.client.force_login(pharmacist)
        self.assertEqual(self.client.get(reverse("pages:about")).status_code, 200)
        self.assertRedirects(self.client.get(reverse("accounts:login")), reverse("pharmacist:dashboard"))

    def test_public_browsing_does_not_grant_customer_cart_access_to_staff(self):
        staff = User.objects.create_user("public-staff@example.test", "Test-pass-42", account_type="staff")
        self.client.force_login(staff)
        for route in ["home", "shop:shop", "pages:about"]:
            self.assertEqual(self.client.get(reverse(route)).status_code, 200)
        self.assertEqual(self.client.get(reverse("shop:cart")).status_code, 403)


    def test_each_public_header_has_one_product_link_in_the_same_order(self):
        from html.parser import HTMLParser
        class Navigation(HTMLParser):
            def __init__(self):
                super().__init__()
                self.inside = False
                self.link = False
                self.labels = []
            def handle_starttag(self, tag, attrs):
                if tag == "nav" or (tag == "ul" and dict(attrs).get("id") == "navLinks"):
                    self.inside = True
                if self.inside and tag == "a":
                    self.link = True
            def handle_endtag(self, tag):
                if tag == "a":
                    self.link = False
                if tag in {"nav", "ul"}:
                    self.inside = False
            def handle_data(self, data):
                if self.inside and self.link and data.strip():
                    self.labels.append(data.strip())
        for route in ["home", "shop:shop", "pages:about", "pages:contact"]:
            with self.subTest(route=route):
                parser = Navigation()
                parser.feed(self.client.get(reverse(route)).content.decode())
                self.assertEqual(parser.labels[:4], ["Home", "Product", "About", "Contact"])
                self.assertEqual(parser.labels.count("Product"), 1)
                self.assertNotIn("Products", parser.labels)
                self.assertNotIn("Shop", parser.labels)
