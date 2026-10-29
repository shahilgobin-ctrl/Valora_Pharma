"""Check the auth flow when the team's Home and Shop routes are mounted."""

import re

from django.core import mail
from django.http import HttpResponse
from django.test import TestCase, override_settings
from django.urls import include, path, reverse

from .models import User


def home(request):
    return HttpResponse("Home")


def shop(request):
    return HttpResponse("Shop")


urlpatterns = [
    path("", home, name="home"),
    path("shop/", include(([path("", shop, name="shop")], "shop"), namespace="shop")),
    path("", include("accounts.urls")),
]


@override_settings(
    ROOT_URLCONF=__name__,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class GuestNavigationTests(TestCase):
    password = "Maple!River42Sun"

    def test_guest_link_and_customer_login_open_home(self):
        page = self.client.get(reverse("accounts:login"))
        self.assertContains(page, 'href="/">Explore Home</a>')
        User.objects.create_user(email="customer@example.com", password=self.password)
        response = self.client.post(reverse("accounts:login"), {
            "email": "customer@example.com", "password": self.password,
        })
        self.assertRedirects(response, reverse("home"))

    def test_registration_and_email_verification_keep_shop_destination(self):
        shop_url = reverse("shop:shop")
        page = self.client.get(reverse("accounts:login"), {"next": shop_url})
        self.assertContains(page, 'name="next" value="/shop/"')
        self.assertContains(page, 'href="/register/?next=%2Fshop%2F"')

        registration = {
            "first_name": "Jamie", "last_name": "Lee", "username": "jamie_lee",
            "date_of_birth": "1995-04-15", "gender": "prefer_not_to_say",
            "email": "jamie@example.com", "phone": "+230 5912-3456",
            "password": self.password, "agree_terms": "on", "next": shop_url,
        }
        response = self.client.post(reverse("accounts:register"), registration)
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=%2Fshop%2F", response["Location"])
        self.assertFalse(User.objects.get(email="jamie@example.com").is_active)

        code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group()
        response = self.client.post(reverse("accounts:email_verify"), {
            "email": "jamie@example.com", "code": code, "next": shop_url,
        })
        self.assertRedirects(response, "/login/?next=%2Fshop%2F", fetch_redirect_response=False)
        response = self.client.post(reverse("accounts:login"), {
            "email": "jamie@example.com", "password": self.password, "next": shop_url,
        })
        self.assertRedirects(response, shop_url)

    def test_untrusted_next_does_not_redirect_after_login(self):
        User.objects.create_user(email="customer@example.com", password=self.password)
        response = self.client.post(reverse("accounts:login"), {
            "email": "customer@example.com", "password": self.password,
            "next": "https://other.example/",
        })
        self.assertRedirects(response, reverse("home"))
