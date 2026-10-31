import os
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from accounts.models import User
from superadmin.models import Role
from superadmin.services import assign_role

class Command(BaseCommand):
    help = "Create optional local reference accounts. Requires VALORA_DEMO_PASSWORD and DEBUG."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo accounts are only allowed with DEBUG enabled.")
        password = os.environ.get("VALORA_DEMO_PASSWORD", "")
        if not password:
            raise CommandError("Set VALORA_DEMO_PASSWORD to a strong local-only password first.")
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages))
        records = [
            ("System", "Administrator", "admin@valora.mu", "super-administrator", True),
            ("Sarah", "Mitchell", "sarah@valora.mu", "customer", True),
            ("Dr. James", "Osei", "james@valora.mu", "pharmacist", True),
            ("Linda", "Boateng", "linda@valora.mu", "pharmacy-manager", True),
            ("Kwame", "Asante", "kwame@valora.mu", "customer", False),
            ("Ama", "Poku", "ama@valora.mu", "pharmacist", True),
            ("Kofi", "Mensah", "kofi@valora.mu", "customer", True),
        ]
        if User.objects.filter(email__in=[row[2] for row in records]).exists():
            raise CommandError("A demo email already exists. No accounts were changed.")
        for first, last, email, key, active in records:
            user = User.objects.create_user(email=email, password=password, first_name=first, last_name=last, is_active=active)
            assign_role(user, Role.objects.get(key=key))
        self.stdout.write(self.style.SUCCESS("Created seven local demo accounts. Administrator: admin@valora.mu"))
