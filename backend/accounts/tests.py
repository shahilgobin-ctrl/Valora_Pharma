"""Behavior and security tests for the customer/staff authentication flows."""
from datetime import date, timedelta
from io import StringIO
import re
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import RegistrationForm
from .models import PasswordResetChallenge, TERMS_VERSION, User


PASSWORD = "Maple!River42Sun"
FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class AuthTestCase(TestCase):
    def setUp(self):
        cache.clear()

    def registration_data(self, **changes):
        data = {
            "first_name": "Jamie",
            "last_name": "Lee",
            "date_of_birth": "15-04-1995",
            "gender": "prefer_not_to_say",
            "email": "Jamie@example.com",
            "phone": "+230 5912-3456",
            "password": PASSWORD,
            "agree_terms": "on",
        }
        data.update(changes)
        return data

    def customer(self, **changes):
        fields = {
            "email": "customer@example.com",
            "first_name": "Jamie",
            "last_name": "Lee",
            "account_type": User.AccountType.CUSTOMER,
        }
        fields.update(changes)
        return User.objects.create_user(password=PASSWORD, **fields)


class RegistrationTests(AuthTestCase):
    def test_customer_registration_saves_profile_and_hashes_password(self):
        response = self.client.post(reverse("accounts:register"), self.registration_data(), follow=True)
        self.assertRedirects(response, reverse("accounts:login"))
        user = User.objects.get()
        self.assertEqual(user.email, "jamie@example.com")
        self.assertEqual(user.first_name, "Jamie")
        self.assertEqual(user.last_name, "Lee")
        self.assertEqual(user.date_of_birth, date(1995, 4, 15))
        self.assertEqual(user.phone, "+23059123456")
        self.assertEqual(user.gender, "prefer_not_to_say")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIsNotNone(user.terms_accepted_at)
        self.assertEqual(user.terms_version, TERMS_VERSION)

    def test_registration_rejects_missing_terms_acceptance(self):
        data = self.registration_data()
        data.pop("agree_terms")
        response = self.client.post(reverse("accounts:register"), data)
        self.assertIn("agree_terms", response.context["form"].errors)
        self.assertFalse(User.objects.exists())

    def test_duplicate_email_is_case_insensitive(self):
        self.customer(email="Jamie@example.com")
        response = self.client.post(reverse("accounts:register"), self.registration_data(email="JAMIE@EXAMPLE.COM"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        self.assertEqual(User.objects.count(), 1)

    def test_database_unique_constraint_covers_writes_bypassing_normalization(self):
        self.customer(email="case@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.bulk_create([User(email="CASE@EXAMPLE.COM")])
        self.assertEqual(User.objects.count(), 1)

    def test_invalid_registration_fields_never_create_user(self):
        invalid_values = {
            "email": "not-an-email",
            "date_of_birth": (timezone.localdate() + timedelta(days=1)).isoformat(),
            "gender": "unexpected-value",
            "phone": "call-me",
            "password": "123",
            "first_name": "",
            "last_name": "",
        }
        for field, value in invalid_values.items():
            with self.subTest(field=field):
                response = self.client.post(reverse("accounts:register"), self.registration_data(**{field: value}))
                self.assertIn(field, response.context["form"].errors)
                self.assertEqual(User.objects.count(), 0)

    def test_both_display_date_and_iso_date_are_accepted(self):
        for submitted in ("15-04-1995", "1995-04-15"):
            with self.subTest(date=submitted):
                form = RegistrationForm(self.registration_data(date_of_birth=submitted))
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data["date_of_birth"], date(1995, 4, 15))

    def test_forged_admin_fields_cannot_elevate_signup(self):
        response = self.client.post(
            reverse("accounts:register"),
            self.registration_data(is_staff="true", is_superuser="true", account_type="staff"),
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get()
        self.assertEqual(user.account_type, User.AccountType.CUSTOMER)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)


class LoginTests(AuthTestCase):
    def test_email_login_is_case_insensitive_and_returns_authenticated_screen(self):
        user = self.customer()
        response = self.client.post(
            reverse("accounts:login"),
            {"email": " CUSTOMER@EXAMPLE.COM ", "password": PASSWORD},
            follow=True,
        )
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
        self.assertTrue(response.context["authenticated"])

    def test_invalid_password_does_not_open_session(self):
        self.customer()
        response = self.client.post(
            reverse("accounts:login"),
            {"email": "customer@example.com", "password": "incorrect"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_customer_cannot_sign_in(self):
        self.customer(is_active=False)
        response = self.client.post(
            reverse("accounts:login"),
            {"email": "customer@example.com", "password": PASSWORD},
        )
        self.assertTrue(response.context["form"].non_field_errors())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_external_next_parameter_never_causes_open_redirect(self):
        self.customer()
        response = self.client.post(
            reverse("accounts:login") + "?next=https://untrusted.example/",
            {"email": "customer@example.com", "password": PASSWORD},
        )
        self.assertEqual(response["Location"], reverse("accounts:login"))

    def test_failure_limit_blocks_authentication_until_counter_expires(self):
        self.customer()
        payload = {"email": "customer@example.com", "password": "incorrect"}
        for _ in range(settings.LOGIN_MAX_FAILURES):
            self.assertEqual(self.client.post(reverse("accounts:login"), payload).status_code, 200)
        with patch("accounts.forms.authenticate") as authenticate:
            response = self.client.post(
                reverse("accounts:login"),
                {"email": "customer@example.com", "password": PASSWORD},
            )
            self.assertEqual(response.status_code, 429)
            authenticate.assert_not_called()
        self.assertNotIn("_auth_user_id", self.client.session)
        # Clearing models expiration in this test without waiting fifteen minutes.
        cache.clear()
        response = self.client.post(
            reverse("accounts:login"),
            {"email": "customer@example.com", "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 302)

    def test_logout_requires_post_and_clears_session(self):
        self.client.force_login(self.customer())
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)


class StaffTests(AuthTestCase):
    def test_staff_signup_is_pending_and_has_no_admin_permissions(self):
        response = self.client.post(reverse("accounts:staff_register"), self.registration_data())
        self.assertRedirects(response, reverse("accounts:login"))
        staff = User.objects.get()
        self.assertEqual(staff.account_type, User.AccountType.STAFF)
        self.assertFalse(staff.is_active)
        self.assertFalse(staff.is_staff)
        self.assertFalse(staff.is_superuser)
        self.assertFalse(staff.groups.exists())
        self.assertFalse(staff.user_permissions.exists())
        pending = self.client.post(
            reverse("accounts:login"),
            {"email": staff.email, "password": PASSWORD},
        )
        self.assertTrue(pending.context["form"].non_field_errors())
        self.assertNotIn("_auth_user_id", self.client.session)

        # An administrator approves the pharmacy staff account by activating it.
        staff.is_active = True
        staff.save(update_fields=["is_active"])
        approved = self.client.post(
            reverse("accounts:login"),
            {"email": staff.email, "password": PASSWORD},
            follow=True,
        )
        self.assertTrue(approved.context["authenticated"])
        self.assertFalse(User.objects.get(pk=staff.pk).is_staff)

    def test_customer_and_approved_staff_share_one_sign_in(self):
        customer = self.customer()
        staff = self.customer(email="staff@example.com", account_type=User.AccountType.STAFF)
        for user in (customer, staff):
            with self.subTest(email=user.email):
                response = self.client.post(
                    reverse("accounts:login"), {"email": user.email, "password": PASSWORD}, follow=True,
                )
                self.assertRedirects(response, reverse("accounts:login"))
                self.assertTrue(response.context["authenticated"])
                self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
                self.client.post(reverse("accounts:logout"))
        self.assertFalse(staff.is_staff)
        self.assertFalse(staff.is_superuser)

    def test_legacy_staff_login_redirects_to_shared_sign_in(self):
        self.client.force_login(self.customer())
        response = self.client.get(reverse("accounts:staff_login"))
        self.assertRedirects(response, reverse("accounts:login"))
        post = self.client.post(reverse("accounts:staff_login"), {"email": "x@y.mu", "password": "x"})
        self.assertEqual(post.status_code, 307)
        self.assertEqual(post["Location"], reverse("accounts:login"))
        self.assertTrue(self.client.get(reverse("accounts:login")).context["authenticated"])

    def test_legacy_staff_login_post_preserves_credentials(self):
        staff = self.customer(email="employee@example.com", account_type=User.AccountType.STAFF)
        response = self.client.post(
            reverse("accounts:staff_login"),
            {"email": staff.email, "password": PASSWORD}, follow=True,
        )
        self.assertTrue(response.context["authenticated"])
        self.assertEqual(self.client.session["_auth_user_id"], str(staff.pk))


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordRecoveryTests(AuthTestCase):
    def request_code(self, *, email="customer@example.com"):
        response = self.client.post(reverse("accounts:password_forgot"), {"email": email})
        self.assertRedirects(response, reverse("accounts:password_verify"))
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(r"\b\d{6}\b", mail.outbox[0].body)
        self.assertIsNotNone(match)
        return match.group()

    def test_customer_can_reset_password_with_emailed_code(self):
        user = self.customer()
        code = self.request_code()
        challenge = PasswordResetChallenge.objects.get()
        self.assertNotIn(code, challenge.code_hash)
        self.assertEqual(mail.outbox[0].to, [user.email])
        self.assertRedirects(
            self.client.post(reverse("accounts:password_verify"), {"code": code}),
            reverse("accounts:password_new"),
        )
        response = self.client.post(reverse("accounts:password_new"), {
            "new_password1": "New!MeadowPath456", "new_password2": "New!MeadowPath456",
        })
        self.assertRedirects(response, reverse("accounts:login"))
        user.refresh_from_db()
        challenge.refresh_from_db()
        self.assertTrue(user.check_password("New!MeadowPath456"))
        self.assertFalse(user.check_password(PASSWORD))
        self.assertIsNotNone(challenge.consumed_at)
        self.assertNotIn("password_reset_flow", self.client.session)
        self.assertRedirects(self.client.get(reverse("accounts:password_new")), reverse("accounts:password_forgot"))

    def test_unknown_and_inactive_accounts_get_generic_response_without_email(self):
        self.customer(email="inactive@example.com", is_active=False)
        for email in ("missing@example.com", "inactive@example.com"):
            with self.subTest(email=email):
                response = self.client.post(reverse("accounts:password_forgot"), {"email": email}, follow=True)
                self.assertRedirects(response, reverse("accounts:password_verify"))
                self.assertContains(response, "If an eligible account exists")
                self.assertEqual(len(mail.outbox), 0)

    def test_wrong_code_attempt_limit_and_expiry(self):
        self.customer()
        correct_code = self.request_code()
        wrong_code = "000000" if correct_code != "000000" else "111111"
        for _ in range(settings.PASSWORD_RESET_MAX_ATTEMPTS):
            response = self.client.post(reverse("accounts:password_verify"), {"code": wrong_code})
            self.assertContains(response, "invalid or expired")
        challenge = PasswordResetChallenge.objects.get()
        self.assertEqual(challenge.attempts, settings.PASSWORD_RESET_MAX_ATTEMPTS)
        self.assertRedirects(
            self.client.post(reverse("accounts:password_verify"), {"code": correct_code}),
            reverse("accounts:password_forgot"),
        )
        cache.clear()
        mail.outbox.clear()
        correct_code = self.request_code()
        challenge = PasswordResetChallenge.objects.latest("pk")
        challenge.expires_at = timezone.now() - timedelta(seconds=1)
        challenge.save(update_fields=["expires_at"])
        self.assertRedirects(
            self.client.post(reverse("accounts:password_verify"), {"code": correct_code}),
            reverse("accounts:password_forgot"),
        )

    def test_code_replay_and_weak_or_mismatched_passwords_are_rejected(self):
        user = self.customer()
        code = self.request_code()
        self.client.post(reverse("accounts:password_verify"), {"code": code})
        self.assertRedirects(
            self.client.post(reverse("accounts:password_verify"), {"code": code}),
            reverse("accounts:password_new"),
        )
        response = self.client.post(reverse("accounts:password_new"), {
            "new_password1": "123", "new_password2": "different",
        })
        self.assertIn("new_password1", response.context["form"].errors)
        self.assertIn("new_password2", response.context["form"].errors)
        user.refresh_from_db()
        self.assertTrue(user.check_password(PASSWORD))

    def test_approved_staff_can_reset_through_shared_recovery(self):
        staff = self.customer(email="employee@example.com", account_type=User.AccountType.STAFF)
        code = self.request_code(email=staff.email)
        self.assertRedirects(
            self.client.post(reverse("accounts:password_verify"), {"code": code}),
            reverse("accounts:password_new"),
        )
        self.assertEqual(PasswordResetChallenge.objects.get().account_type, User.AccountType.STAFF)
        self.assertRedirects(self.client.post(reverse("accounts:password_new"), {
            "new_password1": "New!MeadowPath456", "new_password2": "New!MeadowPath456",
        }), reverse("accounts:login"))
        staff.refresh_from_db()
        self.assertTrue(staff.check_password("New!MeadowPath456"))

    def test_pending_staff_cannot_receive_reset_code(self):
        self.customer(email="pending@example.com", account_type=User.AccountType.STAFF, is_active=False)
        response = self.client.post(reverse("accounts:password_forgot"), {"email": "pending@example.com"}, follow=True)
        self.assertRedirects(response, reverse("accounts:password_verify"))
        self.assertContains(response, "If an eligible account exists")
        self.assertEqual(len(mail.outbox), 0)

    def test_legacy_staff_recovery_urls_preserve_post_and_redirect_to_shared_flow(self):
        for legacy, shared in (
            ("staff_password_forgot", "password_forgot"),
            ("staff_password_verify", "password_verify"),
            ("staff_password_new", "password_new"),
        ):
            with self.subTest(legacy=legacy):
                get_response = self.client.get(reverse("accounts:" + legacy))
                self.assertEqual(get_response.status_code, 302)
                self.assertEqual(get_response["Location"], reverse("accounts:" + shared))
                response = self.client.post(reverse("accounts:" + legacy), {"email": "customer@example.com"})
                self.assertEqual(response.status_code, 307)
                self.assertEqual(response["Location"], reverse("accounts:" + shared))

    def test_legacy_staff_forgot_post_sends_code_through_shared_flow(self):
        staff = self.customer(email="employee@example.com", account_type=User.AccountType.STAFF)
        response = self.client.post(
            reverse("accounts:staff_password_forgot"), {"email": staff.email}, follow=True,
        )
        self.assertEqual(response.redirect_chain[0], (reverse("accounts:password_forgot"), 307))
        self.assertEqual(response.redirect_chain[1], (reverse("accounts:password_verify"), 302))
        self.assertEqual(len(mail.outbox), 1)

    def test_same_email_request_is_throttled(self):
        self.customer()
        self.request_code()
        self.client.post(reverse("accounts:password_forgot"), {"email": "customer@example.com"})
        self.assertEqual(len(mail.outbox), 1)

    def test_recovery_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        for route in ("accounts:password_forgot", "accounts:password_verify", "accounts:password_new"):
            with self.subTest(route=route):
                self.assertEqual(client.post(reverse(route), {"email": "customer@example.com"}).status_code, 403)


class SecurityAndManagementTests(AuthTestCase):
    def test_csrf_is_required_for_signup_login_and_logout(self):
        client = Client(enforce_csrf_checks=True)
        for name in ("accounts:register", "accounts:login", "accounts:logout"):
            with self.subTest(route=name):
                self.assertEqual(client.post(reverse(name), self.registration_data()).status_code, 403)
        client.get(reverse("accounts:register"))
        token = client.cookies["csrftoken"].value
        response = client.post(
            reverse("accounts:register"),
            {**self.registration_data(), "csrfmiddlewaretoken": token},
        )
        self.assertEqual(response.status_code, 302)

    def test_superuser_can_be_created_with_email_for_admin_approval(self):
        user = User.objects.create_superuser("Admin@example.com", PASSWORD)
        self.assertEqual(user.email, "admin@example.com")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertEqual(user.account_type, User.AccountType.STAFF)

    @override_settings(DEBUG=True)
    def test_demo_seed_is_explicit_repeatable_and_hashed(self):
        self.assertFalse(User.objects.exists())
        call_command("seed_demo", stdout=StringIO())
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(User.objects.count(), 1)
        demo = User.objects.get(email="shahil@valora.mu")
        self.assertTrue(demo.check_password("Shahili1234"))
        self.assertFalse(demo.is_staff)
        self.assertFalse(demo.is_superuser)

    @override_settings(DEBUG=False)
    def test_demo_seed_refuses_production(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=StringIO())
        self.assertFalse(User.objects.exists())

    @override_settings(DEBUG=True)
    def test_demo_seed_refuses_existing_administrator(self):
        User.objects.create_superuser("Shahil@valora.mu", PASSWORD)
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=StringIO())
        self.assertTrue(User.objects.get().check_password(PASSWORD))
