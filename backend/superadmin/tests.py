from unittest.mock import patch
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from accounts.models import User
from accounts.access import role_home_name
from .models import AuditLog, Role, SystemSettings
from .services import assign_role

PASSWORD = "Cedar!River42Moon"

@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AdministrationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser(email="admin@example.test", password=PASSWORD)
        self.customer = User.objects.create_user(email="customer@example.test", password=PASSWORD, first_name="Alex", last_name="Lee")
        assign_role(self.customer, Role.objects.get(key="customer"))
        self.client.force_login(self.admin)

    def url(self, name, *args):
        return reverse("superadmin:" + name, args=args)

    def payload(self, **kwargs):
        data = {"first_name": "Jamie", "last_name": "Green", "email": "new@example.test", "phone": "+23059123456", "date_of_birth": "1995-04-15", "gender": "other", "role": Role.objects.get(key="pharmacist").pk, "password": PASSWORD, "is_active": "on"}
        data.update(kwargs)
        return data

    def test_all_pages_render_and_share_sidebar(self):
        for name in ("overview", "users", "roles", "audit", "settings", "user_create"):
            with self.subTest(name=name):
                response = self.client.get(self.url(name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'aria-label="Main navigation"')
                self.assertContains(response, "Sign Out")
        self.assertEqual(self.client.get(self.url("user_detail", self.customer.pk)).status_code, 200)
        self.assertEqual(self.client.get(self.url("user_edit", self.customer.pk)).status_code, 200)
        self.assertEqual(self.client.get(self.url("role_edit", "pharmacist")).status_code, 200)

    def test_anonymous_and_non_admins_cannot_access_governance(self):
        routes = [self.url(name) for name in ("overview", "users", "roles", "audit", "audit_export", "settings", "user_create")]
        self.client.logout()
        for route in routes:
            self.assertEqual(self.client.get(route).status_code, 302)
        self.client.force_login(self.customer)
        for route in routes:
            self.assertEqual(self.client.get(route).status_code, 403)
        self.assertEqual(self.client.post(self.url("user_status", self.admin.pk), {"active": "0"}).status_code, 403)
        self.assertEqual(self.client.post(self.url("user_role", self.customer.pk), {"role": "super-administrator"}).status_code, 403)

    def test_staff_flag_alone_does_not_grant_access(self):
        self.customer.is_staff = True
        self.customer.save()
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(self.url("overview")).status_code, 403)

    def test_manager_role_reuses_access_group_when_permissions_are_edited(self):
        role = Role.objects.get(key="pharmacy-manager")
        self.assertEqual(role.group.name, "Pharmacy Managers")
        manager = User.objects.create_user(email="manager@example.test", password=PASSWORD,
            account_type="staff")
        assign_role(manager, role)
        self.assertEqual(role_home_name(manager), "manager:dashboard")
        self.assertEqual(self.client.post(self.url("role_edit", role.key),
            {"permissions": []}).status_code, 302)
        manager = User.objects.get(pk=manager.pk)
        self.assertTrue(manager.has_perm("manager.access_manager"))
        self.assertEqual(role_home_name(manager), "manager:dashboard")

    def test_staff_with_forged_superuser_flag_cannot_enter_admin_workspace(self):
        forged = User.objects.create_user(email="forged@example.test", password=PASSWORD,
            account_type="staff", is_staff=True, is_superuser=True)
        self.client.force_login(forged)
        self.assertEqual(self.client.get(self.url("overview")).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.url("login"),
            {"email": forged.email, "password": PASSWORD}).status_code, 200)

    def test_create_customer_and_staff_with_hashed_password_and_audit(self):
        for key in ("customer", "pharmacist", "pharmacy-manager", "super-administrator"):
            with self.subTest(role=key):
                payload = self.payload(email="new-" + key + "@example.test", role=Role.objects.get(key=key).pk)
                response = self.client.post(self.url("user_create"), payload)
                self.assertEqual(response.status_code, 302)
                account = User.objects.get(email=payload["email"])
                self.assertTrue(account.check_password(PASSWORD))
                self.assertNotEqual(account.password, PASSWORD)
                self.assertEqual(account.account_type, "customer" if key == "customer" else "admin" if key == "super-administrator" else "staff")
                self.assertEqual(account.is_superuser, key == "super-administrator")
                self.assertTrue(account.groups.filter(portal_role__key=key).exists())
                log = AuditLog.objects.get(action="USER_CREATED", target=account.email)
                self.assertNotIn(PASSWORD, str(log.details))

    def test_duplicate_email_and_weak_password_rejected(self):
        response = self.client.post(self.url("user_create"), self.payload(email="CUSTOMER@example.test"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        response = self.client.post(self.url("user_create"), self.payload(password="123"))
        self.assertIn("password", response.context["form"].errors)
        self.assertFalse(User.objects.filter(email="new@example.test").exists())

    def test_edit_account_preserves_password_when_blank(self):
        before = self.customer.password
        response = self.client.post(self.url("user_edit", self.customer.pk), self.payload(email=self.customer.email, password="", first_name="Updated"))
        self.assertEqual(response.status_code, 302)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.first_name, "Updated")
        self.assertEqual(self.customer.password, before)
        self.assertEqual(AuditLog.objects.get(action="USER_UPDATED").details["changes"]["first_name"]["before"], "Alex")

    def test_invalid_phone_and_future_birth_rejected(self):
        response = self.client.post(self.url("user_create"), self.payload(phone="abc", date_of_birth="2999-01-01"))
        self.assertIn("phone", response.context["form"].errors)
        self.assertIn("date_of_birth", response.context["form"].errors)

    def test_activation_changes_authentication_and_audit(self):
        self.client.post(self.url("user_status", self.customer.pk), {"active": "0"})
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)
        self.assertFalse(Client().login(email=self.customer.email, password=PASSWORD))
        self.assertTrue(AuditLog.objects.filter(action="USER_DEACTIVATED", target=self.customer.email).exists())
        self.client.post(self.url("user_status", self.customer.pk), {"active": "1"})
        self.assertTrue(Client().login(email=self.customer.email, password=PASSWORD))
        self.assertTrue(AuditLog.objects.filter(action="USER_ACTIVATED").exists())

    def test_cannot_deactivate_or_demote_self(self):
        self.client.post(self.url("user_status", self.admin.pk), {"active": "0"})
        self.client.post(self.url("user_role", self.admin.pk), {"role": "customer"})
        response = self.client.post(self.url("user_edit", self.admin.pk), self.payload(email=self.admin.email, role=Role.objects.get(key="customer").pk))
        self.assertContains(response, "cannot deactivate your own account")
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertTrue(self.admin.is_superuser)

    def test_role_assignment_and_permissions_are_effective(self):
        self.client.post(self.url("user_role", self.customer.pk), {"role": "pharmacist"})
        user = User.objects.get(pk=self.customer.pk)
        self.assertTrue(user.has_perm("superadmin.approve_prescriptions"))
        self.assertFalse(user.has_perm("superadmin.manage_cart"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(AuditLog.objects.filter(action="USER_ROLE_CHANGED").exists())
        permission = Permission.objects.get(codename="adjust_stock")
        response = self.client.post(self.url("role_edit", "pharmacist"), {"permissions": [permission.pk]})
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(pk=user.pk)
        self.assertTrue(user.has_perm("superadmin.adjust_stock"))
        self.assertFalse(user.has_perm("superadmin.approve_prescriptions"))
        self.assertTrue(AuditLog.objects.filter(action="ROLE_PERMISSIONS_UPDATED").exists())

    def test_operational_roles_cannot_receive_governance_permissions(self):
        permission = Permission.objects.get(content_type__app_label="accounts", codename="change_user")
        response = self.client.post(self.url("role_edit", "pharmacist"), {"permissions": [permission.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertIn("permissions", response.context["form"].errors)
        self.assertEqual(self.client.post(self.url("role_edit", "super-administrator"), {"permissions": []}).status_code, 400)

    def test_promotion_and_demotion_update_admin_flags(self):
        self.client.post(self.url("user_role", self.customer.pk), {"role": "super-administrator"})
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_staff and self.customer.is_superuser)
        self.assertEqual(self.customer.account_type, "admin")
        self.client.post(self.url("user_role", self.customer.pk), {"role": "pharmacy-manager"})
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_staff or self.customer.is_superuser)
        self.assertEqual(self.customer.account_type, "staff")

    def test_settings_persist_and_disable_public_registration(self):
        self.client.post(self.url("settings"), {"portal_name": "Valora Test", "support_email": "support@example.test", "page_size": 25})
        settings = SystemSettings.current()
        self.assertEqual(settings.portal_name, "Valora Test")
        self.assertEqual(settings.page_size, 25)
        self.assertEqual(self.client.get(reverse("accounts:register")).status_code, 403)
        self.assertEqual(self.client.post(reverse("accounts:staff_register"), {}).status_code, 403)
        self.assertContains(self.client.get(self.url("roles")), "Valora Test")
        self.assertTrue(AuditLog.objects.filter(action="SYSTEM_SETTINGS_UPDATED").exists())
        self.client.post(self.url("settings"), {"portal_name": "Valora Test", "page_size": 10, "customer_registration": "on", "staff_registration": "on"})
        self.assertEqual(self.client.get(reverse("accounts:register")).status_code, 200)

    def test_invalid_settings_do_not_persist(self):
        response = self.client.post(self.url("settings"), {"portal_name": "", "page_size": 999, "support_email": "bad"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SystemSettings.current().portal_name, "ValoraPharma")

    def test_export_filters_and_neutralizes_spreadsheet_formulas(self):
        AuditLog.objects.create(actor=self.admin, actor_email=self.admin.email, action="USER_UPDATED", target="=DANGEROUS()")
        AuditLog.objects.create(actor=self.admin, actor_email=self.admin.email, action="USER_CREATED", target="other")
        response = self.client.get(self.url("audit_export"), {"action": "USER_UPDATED"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        text = response.content.decode("utf-8-sig")
        self.assertIn("'=DANGEROUS()", text)
        self.assertNotIn("USER_CREATED", text)

    def test_audit_uses_remote_address_not_untrusted_forwarded_header(self):
        self.client.post(self.url("user_status", self.customer.pk), {"active": "0"}, REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4")
        self.assertEqual(AuditLog.objects.get(action="USER_DEACTIVATED").ip_address, "127.0.0.1")

    def test_mutations_require_post_and_csrf(self):
        for name in ("user_status", "user_role"):
            self.assertEqual(self.client.get(self.url(name, self.customer.pk)).status_code, 405)
        self.assertEqual(self.client.get(self.url("logout")).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        for name, args, payload in [("user_status", [self.customer.pk], {"active": "0"}), ("user_role", [self.customer.pk], {"role": "pharmacist"}), ("settings", [], {}), ("logout", [], {}), ("role_edit", ["pharmacist"], {}), ("user_create", [], self.payload())]:
            self.assertEqual(client.post(self.url(name, *args), payload).status_code, 403)

    def test_login_logout_and_session_invalidation(self):
        self.client.logout()
        response = self.client.post(self.url("login"), {"email": self.admin.email, "password": PASSWORD})
        self.assertRedirects(response, self.url("overview"))
        self.assertTrue(AuditLog.objects.filter(action="ADMIN_SIGNED_IN").exists())
        self.client.post(self.url("logout"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get(self.url("overview")).status_code, 302)
        self.assertTrue(AuditLog.objects.filter(action="ADMIN_SIGNED_OUT").exists())

    def test_admin_login_rejects_customer_and_inactive_admin(self):
        self.client.logout()
        for user in (self.customer, self.admin):
            if user == self.admin:
                user.is_active = False
                user.save()
            response = self.client.post(self.url("login"), {"email": user.email, "password": PASSWORD})
            self.assertContains(response, "Unable to sign in")
            self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_is_rate_limited(self):
        self.client.logout()
        for _ in range(8):
            self.client.post(self.url("login"), {"email": self.admin.email, "password": "wrong"})
        self.assertEqual(self.client.post(self.url("login"), {"email": self.admin.email, "password": PASSWORD}).status_code, 429)

    def test_overview_counts_are_live_and_users_are_searchable(self):
        response = self.client.get(self.url("overview"))
        self.assertEqual(response.context["total"], 2)
        self.assertEqual(response.context["staff_count"], 1)
        response = self.client.get(self.url("users"), {"q": "Alex"})
        self.assertEqual(response.context["accounts"].paginator.count, 1)
        self.assertContains(response, self.customer.email)

    def test_password_change_keeps_own_admin_session(self):
        response = self.client.post(self.url("user_edit", self.admin.pk), self.payload(email=self.admin.email, role=Role.objects.get(key="super-administrator").pk, password="Other!River42Cedar"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(self.url("overview")).status_code, 200)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password("Other!River42Cedar"))

    def test_audit_failure_rolls_back_account_mutation(self):
        with patch("superadmin.views.audit", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url("user_status", self.customer.pk), {"active": "0"})
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)
