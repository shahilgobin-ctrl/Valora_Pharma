from io import StringIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from inventory.models import Batch
from .models import Order


class WorkflowDemoTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = override_settings(DEBUG=True, MEDIA_ROOT=directory.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.user = get_user_model().objects.create_user(
            email="demo-staff@example.com", account_type="staff"
        )
        group, _ = Group.objects.get_or_create(name="Pharmacist")
        self.user.groups.add(group)

    def test_repeat_preserves_stock_and_orders(self):
        for iteration in range(2):
            call_command(
                "seed_pharmacist_workflows",
                pharmacist=self.user.email,
                stdout=StringIO(),
            )
            self.assertEqual(Order.objects.count(), 2)
            if iteration == 0:
                Batch.objects.update(quantity_available=7)
        self.assertEqual(
            set(Batch.objects.values_list("quantity_available", flat=True)), {7}
        )

    @override_settings(DEBUG=False)
    def test_demo_refuses_production(self):
        with self.assertRaises(CommandError):
            call_command("seed_pharmacist_workflows", pharmacist=self.user.email)

    def test_demo_requires_existing_pharmacist(self):
        with self.assertRaises(CommandError):
            call_command("seed_pharmacist_workflows", pharmacist="missing@example.com")
