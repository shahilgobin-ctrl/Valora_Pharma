import secrets
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from accounts.models import User, canonical_email

class Command(BaseCommand):
    help = "Create one development-only demo customer without changing existing accounts."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo is only available with DJANGO_DEBUG=true.")
        with transaction.atomic():
            email = canonical_email("demo.customer@example.test")
            if User.objects.filter(email=email).exists():
                self.stdout.write("Demo account already exists; no account was changed.")
                return
            password = secrets.token_urlsafe(18)
            user = User.objects.create_user(
                email, password,
                first_name="Demo", last_name="Customer",
                account_type=User.AccountType.CUSTOMER,
                email_verified_at=timezone.now(),
            )
        self.stdout.write(self.style.SUCCESS(f"Development demo created: {user.email} / {password}"))
