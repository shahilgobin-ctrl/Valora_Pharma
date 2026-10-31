"""Compatibility command: synchronise presentation metadata, never sample stock."""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from inventory.models import Medicine
from shop.catalogue import ensure_storefront

class Command(BaseCommand):
    help = "Link existing inventory medicines to storefront metadata without changing medicines or stock."

    def add_arguments(self, parser):
        parser.add_argument("--update-existing", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        if options.get("update_existing"):
            raise CommandError("Sample catalogue replacement is disabled; manage medicines through inventory.")
        for medicine in Medicine.objects.all():
            ensure_storefront(medicine)
        self.stdout.write("Storefront links synchronised; inventory and stock unchanged.")
