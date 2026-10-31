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
            "username": "jamie_lee",
            "date_of_birth": "1995-04-15",
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


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RegistrationTests(AuthTestCase):
    def test_customer_registration_saves_profile_and_hashes_password(self):
        response = self.client.post(reverse("accounts:register"), self.registration_data(), follow=True)
        self.assertEqual(response.resolver_match.view_name, "accounts:login")
        user = User.objects.get()
        self.assertEqual(user.email, "jamie@example.com")
        self.assertEqual(user.first_name, "Jamie")
        self.assertEqual(user.last_name, "Lee")
        self.assertEqual(user.username, "jamie_lee")
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
        self.assertEqual(len(mail.outbox), 0)
        self.assertRedirects(self.client.post(reverse("accounts:login"), {
            "email": user.email, "password": PASSWORD,
        }), reverse("home"))

    def test_customer_email_code_pages_are_removed(self):
        for path in ("/email/verify/", "/email/resend/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
        self.assertNotContains(self.client.get(reverse("accounts:login")), "Resend code")

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

    def test_duplicate_username_is_case_insensitive(self):
        self.customer(username="Jamie_Lee")
        response = self.client.post(reverse("accounts:register"), self.registration_data())
        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)
        self.assertEqual(User.objects.count(), 1)

    def test_database_unique_constraint_covers_writes_bypassing_normalization(self):
        self.customer(email="case@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.bulk_create([User(email="CASE@EXAMPLE.COM")])
        self.assertEqual(User.objects.count(), 1)

    def test_database_username_constraint_is_case_insensitive(self):
        self.customer(username="Jamie_Lee")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.bulk_create([User(email="other@example.com", username="jamie_lee")])
        self.assertEqual(User.objects.count(), 1)

    def test_invalid_registration_fields_never_create_user(self):
        invalid_values = {
            "email": "not-an-email",
            "date_of_birth": (timezone.localdate() + timedelta(days=1)).isoformat(),
            "gender": "unexpected-value",
            "phone": "call-me",
            "password": "123",
            "username": "bad username",
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
    def test_login_page_does_not_publish_demo_credentials(self):
        page = self.client.get(reverse("accounts:login"))
        self.assertNotContains(page, "Shahili1234")
        self.assertNotContains(page, "Customer Demo:")

    def test_email_login_is_case_insensitive_and_opens_customer_area(self):
        user = self.customer()
        response = self.client.post(
            reverse("accounts:login"),
            {"email": " CUSTOMER@EXAMPLE.COM ", "password": PASSWORD},
            follow=True,
        )
        self.assertRedirects(response, reverse("home"))
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
        self.assertTemplateUsed(response, "home.html")

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
        for target in ("https://untrusted.example/", reverse("accounts:staff_landing")):
            with self.subTest(next=target):
                response = self.client.post(
                    reverse("accounts:login") + "?next=" + target,
                    {"email": "customer@example.com", "password": PASSWORD},
                )
                self.assertEqual(response["Location"], reverse("home"))
                self.client.post(reverse("accounts:logout"))

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

    def test_failures_for_one_email_do_not_block_a_neighbor_on_same_ip(self):
        self.customer()
        other = self.customer(email="neighbor@example.com")
        for _ in range(settings.LOGIN_MAX_FAILURES):
            self.client.post(reverse("accounts:login"), {
                "email": "customer@example.com", "password": "incorrect",
            })
        self.assertEqual(self.client.post(reverse("accounts:login"), {
            "email": "customer@example.com", "password": PASSWORD,
        }).status_code, 429)
        self.assertRedirects(self.client.post(reverse("accounts:login"), {
            "email": other.email, "password": PASSWORD,
        }), reverse("home"))

    def test_logout_requires_post_and_clears_session(self):
        self.client.force_login(self.customer())
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)


class StaffTests(AuthTestCase):
    def test_inactive_staff_cannot_sign_in(self):
        staff = self.customer(email="pending@example.com", account_type=User.AccountType.STAFF, is_active=False)
        response = self.client.post(reverse("accounts:login"), {"email": staff.email, "password": PASSWORD})
        self.assertTrue(response.context["form"].non_field_errors())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_public_staff_registration_cannot_create_accounts(self):
        url = reverse("accounts:staff_register")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, self.registration_data()).status_code, 403)
        self.assertFalse(User.objects.exists())

    def test_customer_registration_uses_calendar_and_omits_staff_note(self):
        response = self.client.get(reverse("accounts:register"))
        self.assertNotContains(response, reverse("accounts:staff_register"))
        self.assertNotContains(response, "Staff accounts are created by the pharmacy administrator.")
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'type="date"')

    def test_customer_and_approved_staff_share_one_sign_in(self):
        customer = self.customer()
        staff = self.customer(email="staff@example.com", account_type=User.AccountType.STAFF)
        for user in (customer, staff):
            with self.subTest(email=user.email):
                response = self.client.post(
                    reverse("accounts:login"), {"email": user.email, "password": PASSWORD}, follow=True,
                )
                destination = "accounts:staff_landing" if user == staff else "home"
                self.assertRedirects(response, reverse(destination))
                if user.account_type == "customer":
                    self.assertTemplateUsed(response, "home.html")
                else:
                    self.assertEqual(response.context["landing_role"], user.account_type)
                self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
                self.client.post(reverse("accounts:logout"))
        self.assertFalse(staff.is_staff)
        self.assertFalse(staff.is_superuser)


class SharedRoleTests(AuthTestCase):
    def test_supplier_and_admin_use_the_shared_login_with_separate_access(self):
        supplier = self.customer(email="supplier@example.com", account_type=User.AccountType.SUPPLIER)
        administrator = User.objects.create_superuser("admin@example.com", PASSWORD)
        for user, home, forbidden in (
            (supplier, "accounts:supplier_landing", "staff_landing"),
            (administrator, "superadmin:overview", "supplier_landing"),
        ):
            with self.subTest(role=user.account_type):
                response = self.client.post(reverse("accounts:login"), {
                    "email": user.email, "password": PASSWORD,
                }, follow=True)
                self.assertRedirects(response, reverse(home))
                self.assertEqual(self.client.get(reverse("accounts:" + forbidden)).status_code, 403)
                self.client.post(reverse("accounts:logout"))

    def test_admin_role_without_superuser_permission_cannot_open_admin_area(self):
        forged = self.customer(email="forged@example.com", account_type=User.AccountType.ADMIN)
        self.client.force_login(forged)
        self.assertEqual(self.client.get(reverse("accounts:admin_landing")).status_code, 403)
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 403)

    def test_legacy_staff_login_redirects_to_shared_sign_in(self):
        self.client.force_login(self.customer())
        response = self.client.get(reverse("accounts:staff_login"))
        self.assertRedirects(response, reverse("accounts:login"), fetch_redirect_response=False)
        post = self.client.post(reverse("accounts:staff_login"), {"email": "x@y.mu", "password": "x"})
        self.assertEqual(post.status_code, 307)
        self.assertEqual(post["Location"], reverse("accounts:login"))
        self.assertRedirects(self.client.get(reverse("accounts:login")), reverse("home"))

    def test_legacy_staff_login_post_preserves_credentials(self):
        staff = self.customer(email="employee@example.com", account_type=User.AccountType.STAFF)
        response = self.client.post(
            reverse("accounts:staff_login"),
            {"email": staff.email, "password": PASSWORD}, follow=True,
        )
        self.assertEqual(response.context["landing_role"], User.AccountType.STAFF)
        self.assertEqual(self.client.session["_auth_user_id"], str(staff.pk))


class LandingAccessTests(AuthTestCase):
    def test_anonymous_visitors_are_sent_to_shared_sign_in(self):
        for area in ("customer_landing", "staff_landing", "supplier_landing", "admin_landing"):
            with self.subTest(area=area):
                self.assertRedirects(
                    self.client.get(reverse("accounts:" + area)), reverse("accounts:login"),
                )

    def test_only_matching_account_role_can_open_each_area(self):
        customer = self.customer()
        staff = self.customer(email="staff@example.com", account_type=User.AccountType.STAFF)
        for user, allowed, forbidden in (
            (customer, "customer_landing", "staff_landing"),
            (staff, "staff_landing", "customer_landing"),
        ):
            with self.subTest(role=user.account_type):
                self.client.force_login(user)
                response = self.client.get(reverse("accounts:" + allowed))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["landing_role"], user.account_type)
                self.assertEqual(self.client.get(reverse("accounts:" + forbidden)).status_code, 403)
                self.assertRedirects(self.client.get(reverse("accounts:login")), reverse("home") if user.account_type == User.AccountType.CUSTOMER else reverse("accounts:" + allowed))
                self.client.post(reverse("accounts:logout"))
        self.assertFalse(staff.is_staff)

    def test_role_change_takes_effect_on_next_request(self):
        user = self.customer()
        self.client.force_login(user)
        user.account_type = User.AccountType.STAFF
        user.save(update_fields=["account_type"])
        self.assertEqual(self.client.get(reverse("accounts:customer_landing")).status_code, 403)
        self.assertEqual(self.client.get(reverse("accounts:staff_landing")).status_code, 200)

    def test_deactivated_account_cannot_keep_using_either_area(self):
        user = self.customer()
        self.client.force_login(user)
        user.is_active = False
        user.save(update_fields=["is_active"])
        for area in ("customer_landing", "staff_landing"):
            with self.subTest(area=area):
                self.assertRedirects(self.client.get(reverse("accounts:" + area)), reverse("accounts:login"))

    def test_unrecognized_role_is_denied_without_a_redirect_loop(self):
        user = self.customer()
        user.account_type = "unknown"
        user.save(update_fields=["account_type"])
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 403)
        self.assertEqual(self.client.get(reverse("accounts:customer_landing")).status_code, 403)
        self.assertEqual(self.client.get(reverse("accounts:staff_landing")).status_code, 403)

    def test_login_destination_can_be_wired_to_a_teammate_route(self):
        self.customer()
        routes = {**settings.PHARMACY_ROLE_HOME_ROUTES, "customer": "accounts:terms"}
        with override_settings(PHARMACY_ROLE_HOME_ROUTES=routes):
            response = self.client.post(reverse("accounts:login"), {
                "email": "customer@example.com", "password": PASSWORD,
            })
        self.assertRedirects(response, reverse("accounts:terms"))


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

    def test_supplier_and_administrator_can_use_shared_recovery(self):
        supplier = self.customer(email="supplier@example.com", account_type=User.AccountType.SUPPLIER)
        administrator = User.objects.create_superuser("admin@example.com", PASSWORD)
        for user in (supplier, administrator):
            with self.subTest(role=user.account_type):
                mail.outbox.clear()
                cache.clear()
                code = self.request_code(email=user.email)
                self.assertRedirects(self.client.post(reverse("accounts:password_verify"), {
                    "code": code,
                }), reverse("accounts:password_new"))
                self.assertRedirects(self.client.post(reverse("accounts:password_new"), {
                    "new_password1": "New!MeadowPath456", "new_password2": "New!MeadowPath456",
                }), reverse("accounts:login"))
                user.refresh_from_db()
                self.assertTrue(user.check_password("New!MeadowPath456"))

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

    def test_recovery_requests_for_other_accounts_on_same_ip_are_not_blocked(self):
        for number in range(11):
            user = self.customer(email=f"customer{number}@example.com")
            self.client.post(reverse("accounts:password_forgot"), {"email": user.email})
        self.assertEqual(len(mail.outbox), 11)

    def test_recovery_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        for route in ("accounts:password_forgot", "accounts:password_verify", "accounts:password_new"):
            with self.subTest(route=route):
                self.assertEqual(client.post(reverse(route), {"email": "customer@example.com"}).status_code, 403)


class SecurityAndManagementTests(AuthTestCase):
    def test_administrator_provisions_staff_and_supplier_inactive_without_admin_permissions(self):
        administrator = User.objects.create_superuser("admin@example.com", PASSWORD)
        self.client.force_login(administrator)
        for role in (User.AccountType.STAFF, User.AccountType.SUPPLIER):
            with self.subTest(role=role):
                email = f"new.{role}@example.com"
                response = self.client.post(reverse("admin:accounts_user_add"), {
                    "email": email,
                    "password1": PASSWORD,
                    "password2": PASSWORD,
                    "account_type": role,
                    "is_active": "on",
                    "_save": "Save",
                })
                self.assertEqual(response.status_code, 302)
                account = User.objects.get(email=email)
                self.assertFalse(account.is_active)
                self.assertEqual(account.account_type, role)
                self.assertFalse(account.is_staff)
                self.assertFalse(account.is_superuser)

    def test_only_superuser_can_manage_accounts_or_create_admin_role(self):
        administrator = User.objects.create_superuser("admin@example.com", PASSWORD)
        self.client.force_login(administrator)
        rejected = self.client.post(reverse("admin:accounts_user_add"), {
            "email": "fake.admin@example.com", "password1": PASSWORD,
            "password2": PASSWORD, "account_type": User.AccountType.ADMIN, "_save": "Save",
        })
        self.assertEqual(rejected.status_code, 200)
        self.assertFalse(User.objects.filter(email="fake.admin@example.com").exists())
        self.client.post(reverse("accounts:logout"))
        lesser_admin = self.customer(email="lesser@example.com", account_type=User.AccountType.STAFF, is_staff=True)
        self.client.force_login(lesser_admin)
        self.assertEqual(self.client.get(reverse("admin:accounts_user_add")).status_code, 403)

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
        self.assertEqual(user.account_type, User.AccountType.ADMIN)

    @override_settings(DEBUG=True)
    def test_demo_seed_is_explicit_repeatable_and_hashed(self):
        self.assertFalse(User.objects.exists())
        first_output = StringIO()
        call_command("seed_demo", stdout=first_output)
        demo = User.objects.get(email="demo.customer@example.test")
        first_hash = demo.password
        self.assertIn("Development demo created", first_output.getvalue())
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(User.objects.count(), 1)
        demo.refresh_from_db()
        self.assertEqual(demo.password, first_hash)
        self.assertFalse(demo.is_staff)
        self.assertFalse(demo.is_superuser)

    @override_settings(DEBUG=False)
    def test_demo_seed_refuses_production(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=StringIO())
        self.assertFalse(User.objects.exists())

    @override_settings(DEBUG=True)
    def test_demo_seed_does_not_change_existing_administrator(self):
        User.objects.create_superuser("demo.customer@example.test", PASSWORD)
        call_command("seed_demo", stdout=StringIO())
        self.assertTrue(User.objects.get().check_password(PASSWORD))
