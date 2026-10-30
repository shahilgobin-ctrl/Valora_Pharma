"""The removed email-code flow must not strand earlier customer signups."""

from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class RemoveCustomerEmailVerificationMigrationTests(TransactionTestCase):
    migrate_from = ("accounts", "0004_user_username_and_more")
    migrate_to = ("accounts", "0005_remove_customer_email_verification")

    def test_pending_customer_with_code_becomes_active(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        User = old_apps.get_model("accounts", "User")
        Challenge = old_apps.get_model("accounts", "EmailVerificationChallenge")
        pending = User.objects.create(
            email="pending@example.test", password="unusable", account_type="customer",
            is_active=False,
        )
        separate = User.objects.create(
            email="disabled@example.test", password="unusable", account_type="customer",
            is_active=False,
        )
        Challenge.objects.create(
            user=pending, code_hash="old-code", expires_at=timezone.now() + timedelta(days=1),
        )

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        current_user = executor.loader.project_state([self.migrate_to]).apps.get_model("accounts", "User")
        self.assertTrue(current_user.objects.get(pk=pending.pk).is_active)
        self.assertFalse(current_user.objects.get(pk=separate.pk).is_active)
