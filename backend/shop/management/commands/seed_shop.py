"""Import an explicitly supplied catalogue; never replace existing pharmacy records."""
import json
from pathlib import Path
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify
from shop.models import Category, Product


class Command(BaseCommand):
    help = "Import new catalogue products from a supplied JSON file; existing products are preserved."

    def add_arguments(self, parser):
        parser.add_argument("--catalogue", required=True, help="JSON file containing product objects with a category name")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            rows = json.loads(Path(options["catalogue"]).read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                raise ValueError("Expected a JSON list.")
            created = 0
            for row in rows:
                data = dict(row)
                name = data.pop("category")
                category, _ = Category.objects.get_or_create(name=name, defaults={"slug": slugify(name)})
                slug = data.get("slug") or slugify(data["name"])
                if Product.objects.filter(slug=slug).exists():
                    continue
                product = Product(category=category, **data)
                product.slug = slug
                product.full_clean()
                product.save()
                created += 1
        except (OSError, ValueError, KeyError, TypeError, ValidationError) as error:
            raise CommandError(f"Catalogue not imported: {error}") from error
        self.stdout.write(self.style.SUCCESS(f"Imported {created} new medicines; existing records preserved."))
