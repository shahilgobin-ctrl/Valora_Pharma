"""Add repeatable fictional pharmacy records to the local SQLite database."""
from datetime import timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from inventory.models import Medicine, Batch
from orders.models import Order
from orders.services import create_order
from prescriptions.models import Prescription
from prescriptions.sample_documents import create_demo_pdf

# Descriptive demonstration catalogue; prices and stock are fictional.
CATALOGUE = [
    ("Paracetamol", "500 mg", "Tablet", "Pain relief", False, "3.50"),
    ("Ibuprofen", "200 mg", "Tablet", "Pain relief", False, "4.25"),
    ("Cetirizine", "10 mg", "Tablet", "Allergy", False, "5.50"),
    ("Loratadine", "10 mg", "Tablet", "Allergy", False, "5.00"),
    ("Oral Rehydration Salts", "Standard sachet", "Powder", "Hydration", False, "7.50"),
    ("Saline Nasal Spray", "0.9%", "Spray", "Nasal care", False, "8.00"),
    ("Antacid", "500 mg", "Chewable Tablet", "Digestive care", False, "3.75"),
    ("Vitamin C", "500 mg", "Tablet", "Vitamins", False, "6.00"),
    ("Zinc", "20 mg", "Tablet", "Vitamins", False, "4.90"),
    ("Clotrimazole", "1%", "Cream", "Skin care", False, "12.50"),
    ("Calamine Lotion", "100 ml", "Lotion", "Skin care", False, "15.00"),
    ("Glycerin", "100 ml", "Solution", "Skin care", False, "9.00"),
    ("Throat Lozenges", "Standard", "Lozenge", "Cold and flu", False, "4.00"),
    ("Vitamin D", "400 IU", "Tablet", "Vitamins", False, "8.50"),
    ("Petroleum Jelly", "100 g", "Ointment", "Skin care", False, "10.00"),
    ("Amoxicillin", "500 mg", "Capsule", "Antibiotic", True, "14.00"),
    ("Metformin", "500 mg", "Tablet", "Diabetes", True, "8.00"),
    ("Amlodipine", "5 mg", "Tablet", "Cardiovascular", True, "9.00"),
    ("Atorvastatin", "20 mg", "Tablet", "Cardiovascular", True, "11.00"),
    ("Omeprazole", "20 mg", "Capsule", "Digestive care", True, "7.50"),
    ("Losartan", "50 mg", "Tablet", "Cardiovascular", True, "10.50"),
    ("Doxycycline", "100 mg", "Capsule", "Antibiotic", True, "13.00"),
    ("Levothyroxine", "50 mcg", "Tablet", "Endocrine", True, "6.50"),
    ("Salbutamol Inhaler", "100 mcg/dose", "Inhaler", "Respiratory", True, "35.00"),
    ("Gliclazide", "80 mg", "Tablet", "Diabetes", True, "12.00"),
]


class Command(BaseCommand):
    help = "Seed fictional pharmacy data without changing existing orders, stock, or pharmacist accounts."

    def add_arguments(self, parser):
        parser.add_argument("--pharmacist", required=True, help="Existing authorized pharmacist email")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("This seed command is only allowed in DEBUG mode.")
        User = get_user_model()
        staff = User.objects.filter(
            email=options["pharmacist"].strip().lower(),
            account_type="staff", is_active=True,
            groups__name="Pharmacist",
        ).first()
        if staff is None:
            raise CommandError("The supplied account must be an active pharmacist.")

        saved_files = []
        counts = {"medicines": 0, "batches": 0, "customers": 0, "prescriptions": 0, "orders": 0}
        try:
            with transaction.atomic():
                medicines = []
                today = timezone.localdate()
                for index, (name, strength, form, category, rx, price) in enumerate(CATALOGUE):
                    medicine, made = Medicine.objects.get_or_create(
                        name=name, strength=strength, dosage_form=form,
                        defaults={
                            "category_name": category,
                            "description": "Fictional catalogue item for a university demonstration; not clinical advice.",
                            "prescription_required": rx,
                            "selling_price": Decimal(price),
                            "reorder_level": 15,
                        },
                    )
                    if made:
                        counts["medicines"] += 1
                    medicines.append(medicine)
                    # Two batches per medicine; special low-stock and near-expiry cases.
                    for b in range(2):
                        qty = 5 if (index == 2 and b == 0) else (12 if (index == 4 and b == 0) else 100)
                        expiry_days = 16 if (index == 5 and b == 0) else (180 if b == 0 else 390)
                        _, made = Batch.objects.get_or_create(
                            medicine=medicine,
                            batch_number=f"VAL-DEMO-{index + 1:02d}-{b + 1}",
                            defaults={
                                "supplier_name": "Valora Fictional Demo Supplier",
                                "received_date": today,
                                "expiry_date": today + timedelta(days=expiry_days),
                                "quantity_available": qty,
                                "purchase_price": (Decimal(price) * Decimal("0.60")).quantize(Decimal("0.01")),
                            },
                        )
                        if made:
                            counts["batches"] += 1

                customers = []
                for index in range(10):
                    email = f"valora-demo-customer-{index + 1:02d}@example.invalid"
                    customer, made = User.objects.get_or_create(
                        email=email,
                        defaults={
                            "first_name": f"Demo{index + 1}",
                            "last_name": "Customer",
                            "account_type": "customer",
                            "is_active": False,
                            "is_staff": False,
                            "is_superuser": False,
                        },
                    )
                    if customer.account_type != "customer":
                        raise CommandError(f"Refusing to use a non-customer account: {email}")
                    if made:
                        customer.set_unusable_password()
                        customer.save(update_fields=["password"])
                        counts["customers"] += 1
                    customers.append(customer)

                for index in range(12):
                    customer = customers[index % len(customers)]
                    target = 2 if index >= 10 else 1
                    if Prescription.objects.filter(customer=customer).count() >= target:
                        continue
                    p = Prescription(customer=customer)
                    p.document.save(f"demo-{index + 1:02d}.pdf", ContentFile(create_demo_pdf(f"Fictional scenario {index + 1}")), save=False)
                    saved_files.append((p.document.storage, p.document.name))
                    p.full_clean()
                    p.save()
                    counts["prescriptions"] += 1

                # Fixed submission keys prevent creating duplicate online orders on reruns.
                prescriptions = list(
                    Prescription.objects.filter(customer__in=customers).order_by("pk")
                )
                for index in range(15):
                    key = uuid5(NAMESPACE_URL, f"valora-demo-dataset-v1-online-{index}")
                    if Order.objects.filter(submission_key=key).exists():
                        continue
                    customer = customers[index % len(customers)]
                    rx = index % 3 == 2
                    medicine = medicines[15 + (index % 10)] if rx else medicines[index % 15]
                    rx_document = None
                    if rx:
                        # One prescription can only be linked to one order.
                        # Pick an available prescription belonging to this customer.
                        rx_document = Prescription.objects.filter(
                            customer=customer, order__isnull=True,
                        ).order_by("pk").first()
                        if rx_document is None:
                            rx_document = Prescription(customer=customer)
                            rx_document.document.save(
                                f"valora-online-{index:02d}.pdf",
                                ContentFile(create_demo_pdf(f"Fictional online order {index + 1}")),
                                save=False,
                            )
                            saved_files.append((rx_document.document.storage, rx_document.document.name))
                            rx_document.full_clean()
                            rx_document.save()
                            counts["prescriptions"] += 1
                    create_order(
                        user=staff, kind=Order.Kind.ONLINE,
                        customer=customer, prescription=rx_document,
                        contact_name=f"Demo Customer {index % 10 + 1}",
                        contact_phone=f"+2305555{index + 100:04d}",
                        pickup_time=timezone.now() + timedelta(days=1 + index % 5),
                        submission_key=key,
                        lines=[{"medicine": medicine, "quantity": 1 + index % 4}],
                    )
                    counts["orders"] += 1
        except Exception:
            for storage, name in saved_files:
                storage.delete(name)
            raise

        self.stdout.write(self.style.SUCCESS("Fictional demo data seeded successfully."))
        for label, number in counts.items():
            self.stdout.write(f"New {label}: {number}")
        self.stdout.write("Existing records, statuses, pharmacist credentials and stock were not reset.")
