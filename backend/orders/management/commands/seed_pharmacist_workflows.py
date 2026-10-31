from datetime import timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from inventory.models import Batch, Medicine
from prescriptions.models import Prescription
from prescriptions.management.commands.seed_prescription_demo import create_demo_pdf
from orders.models import Order
from orders.services import create_order


class Command(BaseCommand):
    help = "Create fictional medicines, stock and two online orders without resetting existing data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pharmacist",
            required=True,
            help="Email of an existing active pharmacist.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo data is available only with DEBUG=True.")
        users = get_user_model()
        staff = users.objects.filter(
            email=options["pharmacist"].strip().lower(),
            account_type="staff",
            is_active=True,
            groups__name="Pharmacist",
        ).first()
        if not staff:
            raise CommandError(
                "Create and activate this Pharmacist account in admin first."
            )
        saved_files = []
        try:
            with transaction.atomic():
                customer, created = users.objects.get_or_create(
                    email="workflow-demo@example.invalid",
                    defaults={
                        "first_name": "Workflow",
                        "last_name": "Demo",
                        "account_type": "customer",
                        "is_active": False,
                    },
                )
                if customer.account_type != "customer":
                    raise CommandError("The demo email belongs to a staff account.")
                if created:
                    customer.set_unusable_password()
                    customer.save(update_fields=["password"])
                medicines = []
                for code, name, rx, price in [
                    ("OTC", "Demo OTC medicine", False, "2.50"),
                    ("RX", "Demo prescription medicine", True, "8.00"),
                ]:
                    medicine, _ = Medicine.objects.get_or_create(
                        name=name,
                        strength="Demo strength",
                        dosage_form="Tablet",
                        defaults={
                            "selling_price": Decimal(price),
                            "prescription_required": rx,
                            "description": "Fictional university test item.",
                        },
                    )
                    medicines.append(medicine)
                    for suffix in ("A", "B"):
                        Batch.objects.get_or_create(
                            medicine=medicine,
                            batch_number=f"DEMO-{code}-{suffix}",
                            defaults={
                                "supplier_name": "Fictional supplier",
                                "purchase_price": Decimal("1.00"),
                                "quantity_available": 100,
                                "expiry_date": timezone.localdate()
                                + timedelta(days=180),
                            },
                        )
                for index, medicine in enumerate(medicines):
                    key = uuid5(NAMESPACE_URL, f"valora-pharmacist-demo-order-{index}")
                    if Order.objects.filter(submission_key=key).exists():
                        continue
                    prescription = None
                    if medicine.prescription_required:
                        prescription = Prescription(customer=customer)
                        prescription.document.save(
                            "workflow-demo.pdf",
                            ContentFile(create_demo_pdf("Online order review")),
                            save=False,
                        )
                        saved_files.append(
                            (prescription.document.storage, prescription.document.name)
                        )
                        prescription.full_clean()
                        prescription.save()
                    order = create_order(
                        user=staff,
                        kind="online",
                        customer=customer,
                        prescription=prescription,
                        contact_name="Workflow Demo",
                        contact_phone="+23055551234",
                        pickup_time=timezone.now() + timedelta(hours=2),
                        submission_key=key,
                        lines=[{"medicine": medicine, "quantity": 4}],
                    )
                    self.stdout.write(
                        f"Created {order}: /pharmacist/orders/{order.pk}/"
                    )
        except Exception:
            for storage, name in saved_files:
                storage.delete(name)
            raise
        self.stdout.write(
            self.style.SUCCESS(
                "Demo data ready. Existing decisions, stock and payments were preserved."
            )
        )
