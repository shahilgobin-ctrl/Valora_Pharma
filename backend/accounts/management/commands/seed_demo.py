from datetime import date
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from accounts.models import User, canonical_email

class Command(BaseCommand):
    help = "Explicitly create/reset the local development customer account."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo is only available with DJANGO_DEBUG=true.")
        with transaction.atomic():
            user, _created = User.objects.get_or_create(email=canonical_email("Shahil@valora.mu"))
            if user.is_staff or user.is_superuser or user.account_type != User.AccountType.CUSTOMER:
                raise CommandError("Refusing to change an existing staff or administrator account.")
            user.first_name = "Shahil"
            user.last_name = "Gobin"
            user.date_of_birth = date(2000, 1, 1)
            user.gender = User.Gender.PREFER_NOT_TO_SAY
            user.phone = "+23051234567"
            user.account_type = User.AccountType.CUSTOMER
            user.is_active = True
            user.set_password("Shahili1234")
            user.save()
        self.stdout.write(self.style.SUCCESS("Demo customer ready: Shahil@valora.mu / Shahili1234 (development only)."))
