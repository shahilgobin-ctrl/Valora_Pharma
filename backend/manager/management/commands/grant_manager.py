from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Grant manager access to an existing active staff account; creates no users or passwords."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(email__iexact=options["email"]).first()
        if not user or not user.is_active or user.account_type not in {"staff", "admin"}:
            raise CommandError("Use an existing active staff/administrator account.")
        user.groups.add(Group.objects.get(name="Pharmacy Managers"))
        self.stdout.write(self.style.SUCCESS("Pharmacy Manager access granted."))
