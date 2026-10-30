"""Shared authentication must preserve the pharmacist area's group boundary."""
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .admin import AdminUserChangeForm
from .models import User


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PharmacistAuthenticationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            "pharmacist@example.test", "Maple!River42Sun", account_type="staff",
        )
        self.user.groups.add(Group.objects.create(name="Pharmacist"))

    def test_shared_login_and_authenticated_login_reach_dashboard(self):
        response = self.client.post(reverse("accounts:login"), {
            "email": self.user.email, "password": "Maple!River42Sun",
            "next": "https://untrusted.example/",
        })
        self.assertRedirects(response, reverse("pharmacist:dashboard"))
        self.assertRedirects(self.client.get(reverse("accounts:login")),
                             reverse("pharmacist:dashboard"))

    def test_legacy_staff_login_reaches_dashboard(self):
        response = self.client.post(reverse("accounts:staff_login"), {
            "email": self.user.email, "password": "Maple!River42Sun",
        }, follow=True)
        self.assertEqual(response.resolver_match.view_name, "pharmacist:dashboard")

    def test_group_alone_does_not_grant_customer_access(self):
        self.user.account_type = "customer"
        self.user.save()
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get(reverse("accounts:login")),
                             reverse("home"))
        self.assertEqual(self.client.get(reverse("pharmacist:dashboard")).status_code, 403)

    def test_inactive_pharmacist_cannot_sign_in(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.post(reverse("accounts:login"), {
            "email": self.user.email, "password": "Maple!River42Sun",
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_administrator_can_be_edited_without_staff_role(self):
        administrator = User.objects.create_superuser("admin@example.test", "Maple!River42Sun")
        form = AdminUserChangeForm(instance=administrator, data={
            "email": administrator.email, "account_type": "admin",
            "is_active": "on", "is_staff": "on", "is_superuser": "on",
            "date_joined": administrator.date_joined.strftime("%Y-%m-%d %H:%M:%S"),
        })
        self.assertTrue(form.is_valid(), form.errors)
