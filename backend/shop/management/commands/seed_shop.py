"""Explicitly import sample catalogue data; never run during page requests."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from shop.models import Category, Product


class Command(BaseCommand):
    help = "Import optional demo catalogue data, preserving existing products by default."

    def add_arguments(self, parser):
        parser.add_argument("--update-existing", action="store_true",
                            help="Explicitly replace existing products with the sample data.")

    @transaction.atomic
    def handle(self, *args, **options):
        source = Path(__file__).resolve().parents[2] / "data" / "demo_catalogue.json"
        rows = json.loads(source.read_text(encoding="utf-8"))
        created_count = 0
        for record in rows:
            data = record.copy()
            homepage_image = data.pop("homepage_image", "")
            category_name = data.pop("category")
            slug = data.pop("slug")
            category_defaults = {"slug": slugify(category_name),
                                 "image": data.pop("category_image", ""),
                                 "display_order": data.pop("category_order", 100)}
            category, _ = Category.objects.get_or_create(
                name=category_name, defaults=category_defaults
            )
            data["category"] = category
            data["is_active"] = True
            operation = Product.objects.update_or_create if options["update_existing"] else Product.objects.get_or_create
            product, created = operation(slug=slug, defaults=data)
            if homepage_image:
                from pages.models import HomepageProductImage
                HomepageProductImage.objects.get_or_create(
                    product=product, defaults={"image": homepage_image}
                )
            created_count += created
        self.stdout.write(self.style.SUCCESS(
            f"Imported {created_count} new sample products; existing products "
            + ("updated by explicit request." if options["update_existing"] else "preserved.")
        ))
