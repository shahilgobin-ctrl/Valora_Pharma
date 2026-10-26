"""Create a repeatable fictional pharmacy dataset for development."""

import sqlite3
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from inventory.models import Batch, Medicine
from orders.models import (
    Allocation,
    Order,
    OrderItem,
    OrderStatusEvent,
    Payment,
    StockMovement,
)
from orders.services import (
    advance_order,
    cancel_order,
    complete_order,
    create_order,
    save_allocations,
)
from pharmacist.models import PharmacyProfile
from prescriptions.models import Prescription
from prescriptions.sample_documents import create_demo_pdf


# ---------------------------------------------------------------------------
# Fictional training data
#
# Prices are illustrative MUR amounts per selling unit, not market quotations.
# Prescription flags represent application scenarios, not dispensing guidance.
# ---------------------------------------------------------------------------

DATASET = "valora-realistic-v1"
ORDER_COUNT = 36

CATALOGUE = [
    ("Paracetamol", "500 mg", "Tablet", "Pain relief", False, "3.50"),
    ("Ibuprofen", "200 mg", "Tablet", "Pain relief", False, "4.25"),
    ("Cetirizine", "10 mg", "Tablet", "Allergy", False, "5.50"),
    ("Loratadine", "10 mg", "Tablet", "Allergy", False, "5.00"),
    (
        "Oral Rehydration Salts",
        "Standard sachet",
        "Powder",
        "Hydration",
        False,
        "7.50",
    ),
    ("Saline Nasal Spray", "0.9%", "Spray", "Nasal care", False, "145.00"),
    ("Antacid", "500 mg", "Chewable Tablet", "Digestive care", False, "3.75"),
    ("Vitamin C", "500 mg", "Tablet", "Vitamins", False, "6.00"),
    ("Zinc", "20 mg", "Tablet", "Vitamins", False, "4.90"),
    ("Clotrimazole", "1%", "Cream", "Skin care", False, "125.00"),
    ("Calamine Lotion", "100 ml", "Lotion", "Skin care", False, "150.00"),
    ("Glycerin", "100 ml", "Solution", "Skin care", False, "90.00"),
    ("Throat Lozenges", "Standard", "Lozenge", "Cold and flu", False, "4.00"),
    ("Vitamin D", "400 IU", "Tablet", "Vitamins", False, "8.50"),
    ("Petroleum Jelly", "100 g", "Ointment", "Skin care", False, "100.00"),
    ("Amoxicillin", "500 mg", "Capsule", "Antibiotic", True, "14.00"),
    ("Metformin", "500 mg", "Tablet", "Diabetes", True, "8.00"),
    ("Amlodipine", "5 mg", "Tablet", "Cardiovascular", True, "9.00"),
    ("Atorvastatin", "20 mg", "Tablet", "Cardiovascular", True, "11.00"),
    ("Omeprazole", "20 mg", "Capsule", "Digestive care", True, "7.50"),
    ("Losartan", "50 mg", "Tablet", "Cardiovascular", True, "10.50"),
    ("Doxycycline", "100 mg", "Capsule", "Antibiotic", True, "13.00"),
    ("Levothyroxine", "50 mcg", "Tablet", "Endocrine", True, "6.50"),
    (
        "Salbutamol Inhaler",
        "100 mcg/dose",
        "Inhaler",
        "Respiratory",
        True,
        "350.00",
    ),
    ("Gliclazide", "80 mg", "Tablet", "Diabetes", True, "12.00"),
]

CUSTOMERS = [
    ("Anjali", "Raman"),
    ("Kevin", "Morel"),
    ("Aisha", "Dawood"),
    ("Nicolas", "Laurent"),
    ("Priya", "Seewoo"),
    ("Yusuf", "Adam"),
    ("Emma", "Hoarau"),
    ("Ravi", "Nair"),
    ("Sarah", "Chan"),
    ("Dylan", "Payet"),
    ("Meera", "Pillay"),
    ("Adam", "Joseph"),
    ("Chloe", "Wong"),
    ("Sameer", "Ali"),
    ("Lea", "Robert"),
    ("Kiran", "Ramsamy"),
    ("Sonia", "Lee"),
    ("Marc", "Duval"),
]

SUPPLIERS = (
    "Lagoon Medical Distribution (fictional)",
    "Central Healthcare Supply (fictional)",
    "Island Pharmaceutical Logistics (fictional)",
)

SELLING_UNITS = {
    "Tablet": "tablet",
    "Capsule": "capsule",
    "Powder": "sachet",
    "Spray": "bottle",
    "Chewable Tablet": "tablet",
    "Cream": "tube",
    "Lotion": "bottle",
    "Solution": "bottle",
    "Lozenge": "lozenge",
    "Ointment": "jar",
    "Inhaler": "inhaler",
}


# ---------------------------------------------------------------------------
# Dataset identification and backup
# ---------------------------------------------------------------------------


def order_key(index):
    """Return a stable submission key so ordinary reruns are harmless."""
    return uuid5(NAMESPACE_URL, f"{DATASET}-order-{index}")


def backup_database(destination):
    """Back up SQLite before an explicitly requested replacement."""
    if connection.vendor != "sqlite" or connection.in_atomic_block:
        raise CommandError(
            "Replacement requires a standalone SQLite database."
        )

    source = Path(connection.settings_dict["NAME"]).resolve()
    target = Path(destination).expanduser().resolve()

    if not source.is_file() or target == source:
        raise CommandError(
            "Choose a different backup path for an existing database."
        )

    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        target.touch(exist_ok=False, mode=0o600)
    except FileExistsError as error:
        raise CommandError(
            "Backup file already exists; choose a new filename."
        ) from error

    try:
        connection.ensure_connection()

        with sqlite3.connect(target) as backup:
            connection.connection.backup(backup)

    except Exception:
        target.unlink(missing_ok=True)
        raise

    return target


def clear_operational_records():
    """Clear business records while preserving accounts and uploaded bytes."""
    for model in (
        StockMovement,
        Payment,
        Allocation,
        OrderStatusEvent,
        OrderItem,
        Order,
        Prescription,
        Batch,
        Medicine,
    ):
        model.objects.all().delete()


# ---------------------------------------------------------------------------
# Management command
# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = (
        "Seed fictional pharmacy records; optionally replace development "
        "business data with a mandatory backup."
    )

    def add_arguments(self, parser):
        parser.add_argument("--pharmacist", required=True)

        parser.add_argument(
            "--replace-development-data",
            action="store_true",
            help=(
                "Delete ALL orders, payments, stock and prescriptions; "
                "keep accounts and files."
            ),
        )

        parser.add_argument(
            "--backup",
            help="New SQLite backup filename required for replacement.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "This command is restricted to DEBUG=True "
                "development databases."
            )

        staff = (
            get_user_model()
            .objects.filter(
                email=options["pharmacist"].strip().lower(),
                account_type="staff",
                is_active=True,
                groups__name="Pharmacist",
            )
            .first()
        )

        if not staff:
            raise CommandError(
                "Supply an existing active staff account "
                "in the Pharmacist group."
            )

        replace = options["replace_development_data"]

        if replace and not options["backup"]:
            raise CommandError(
                "Replacement requires --backup "
                "with a new SQLite backup path."
            )

        if options["backup"] and not replace:
            raise CommandError(
                "--backup is only used with --replace-development-data."
            )

        if not replace:
            existing = Order.objects.filter(
                submission_key__in=[
                    order_key(index)
                    for index in range(ORDER_COUNT)
                ]
            ).count()

            if existing == ORDER_COUNT:
                self.stdout.write(
                    "Dataset already installed; "
                    "decisions, payments and stock preserved."
                )
                return

            if any(
                model.objects.exists()
                for model in (Order, Prescription, Medicine, Batch)
            ):
                raise CommandError(
                    "Use an empty business database or explicitly "
                    "replace development data with a backup."
                )

        if replace:
            backup = backup_database(options["backup"])
            self.stdout.write(f"Database backup created: {backup}")

        saved_files = []

        try:
            with transaction.atomic():
                if replace:
                    clear_operational_records()

                self.build_dataset(staff, saved_files)

        except Exception:
            # Database rollback does not remove files from storage.
            for storage, name in saved_files:
                storage.delete(name)
            raise

        self.stdout.write(
            self.style.SUCCESS(
                "Installed 25 medicines, 52 batches, "
                "18 fictional customers and 36 orders. "
                "Accounts and existing uploaded file bytes were preserved."
            )
        )

    def build_dataset(self, staff, saved_files):
        now = timezone.now()
        today = timezone.localdate()

        PharmacyProfile.objects.get_or_create(
            pk=1,
            defaults={
                "name": "Valora Pharma",
                "address": "Port Louis, Mauritius",
                "receipt_footer": "Thank you for visiting Valora Pharma.",
            },
        )

        medicines = self.create_medicines(today)
        customers = self.create_customers()

        self.create_orders(
            staff,
            customers,
            medicines,
            now,
            today,
            saved_files,
        )

        # Include prescriptions that have not yet been linked to an order.
        statuses = (
            "pending",
            "approved",
            "rejected",
            "pending",
            "approved",
            "pending",
        )

        for index, status in enumerate(statuses):
            self.make_prescription(
                customers[index],
                staff,
                status,
                now - timedelta(hours=1 + index),
                saved_files,
            )

    def create_medicines(self, today):
        medicines = []

        for index, row in enumerate(CATALOGUE):
            name, strength, form, category, rx, price = row

            medicine = Medicine.objects.create(
                name=name,
                strength=strength,
                dosage_form=form,
                category_name=category,
                selling_unit=SELLING_UNITS[form],
                prescription_required=rx,
                selling_price=Decimal(price),
                reorder_level=15,
                description=(
                    "Fictional training catalogue. Price is per "
                    "tablet/capsule or per container/device; "
                    "not a market quotation."
                ),
                is_active=index != 24,
            )
            medicines.append(medicine)

            for batch_index in range(2):
                quantity = (
                    0
                    if index == 13
                    else 3
                    if index == 14
                    else 180 + index * 7
                )

                expiry_days = (
                    14
                    if index == 5 and batch_index == 0
                    else 210 + batch_index * 240
                )

                Batch.objects.create(
                    medicine=medicine,
                    batch_number=(
                        f"VP-{today.year}-{index + 1:03d}-{batch_index + 1}"
                    ),
                    supplier_name=SUPPLIERS[index % len(SUPPLIERS)],
                    received_date=today - timedelta(days=45),
                    expiry_date=today + timedelta(days=expiry_days),
                    quantity_available=quantity,
                    purchase_price=(
                        Decimal(price) * Decimal("0.62")
                    ).quantize(Decimal("0.01")),
                )

        # Include an expired batch and one expiring today.
        for days in (-10, 0):
            Batch.objects.create(
                medicine=medicines[0],
                batch_number=f"VP-QUARANTINE-{abs(days)}",
                supplier_name=SUPPLIERS[0],
                received_date=today - timedelta(days=400),
                expiry_date=today + timedelta(days=days),
                quantity_available=20,
                purchase_price="1.75",
            )

        return medicines

    def create_customers(self):
        customers = []

        for first, last in CUSTOMERS:
            email = (
                f"{first.lower()}.{last.lower()}."
                f"{DATASET}@example.invalid"
            )

            customer, created = get_user_model().objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "account_type": "customer",
                },
            )

            if customer.account_type != "customer":
                raise CommandError(
                    "A fixture email is already assigned to a staff account."
                )

            if created:
                customer.set_unusable_password()
                customer.save(update_fields=["password"])

            customers.append(customer)

        return customers

    def create_orders(
        self,
        staff,
        customers,
        medicines,
        now,
        today,
        saved_files,
    ):
        stages = [
            "pending",
            "confirmed",
            "preparing",
            "ready",
            "completed",
            "cancelled",
        ]

        for index in range(ORDER_COUNT):
            customer = customers[index % len(customers)]
            stage = stages[index % len(stages)]
            walk_in = index >= 24

            if walk_in:
                stage = "completed" if index % 3 else "pending"

            created_at = now - timedelta(
                days=index % 14,
                hours=2,
            )

            medicine = medicines[index % 12]
            prescription = None

            if index % 3 == 1 or (
                not walk_in and stage == "cancelled"
            ):
                medicine = medicines[15 + index % 8]
                status = (
                    "approved"
                    if stage != "cancelled"
                    else "rejected"
                )

                prescription = self.make_prescription(
                    customer,
                    staff,
                    status,
                    created_at,
                    saved_files,
                )

            elif index in (0, 6):
                medicine = medicines[15]

                prescription = self.make_prescription(
                    customer,
                    staff,
                    "pending" if index == 0 else "rejected",
                    created_at,
                    saved_files,
                )

            order = create_order(
                user=staff,
                kind="walk_in" if walk_in else "online",
                customer=customer,
                prescription=prescription,
                contact_name=customer.get_full_name(),
                pickup_time=(
                    None
                    if walk_in
                    else created_at + timedelta(hours=4)
                ),
                submission_key=order_key(index),
                lines=[
                    {
                        "medicine": medicine,
                        "quantity": 2 + index % 4,
                    },
                    {
                        "medicine": medicines[12],
                        "quantity": 3,
                    },
                ],
            )

            if stage == "cancelled":
                cancel_order(
                    order.pk,
                    "Customer withdrew the request after prescription review.",
                    staff,
                )

            elif stage != "pending":
                if not walk_in:
                    advance_order(order.pk, "confirmed", staff)

                    if stage != "confirmed":
                        advance_order(order.pk, "preparing", staff)

                if walk_in or stage in (
                    "preparing",
                    "ready",
                    "completed",
                ):
                    allocations = self.allocate_fixture_order(
                        order,
                        today,
                        split=index == 4,
                    )

                    save_allocations(
                        order.pk,
                        allocations,
                        staff,
                    )

                if not walk_in and stage in ("ready", "completed"):
                    advance_order(order.pk, "ready", staff)

                if stage == "completed":
                    method = "card" if index % 2 else "cash"

                    complete_order(
                        order.pk,
                        method,
                        (
                            order.total_amount + Decimal("50.00")
                            if method == "cash"
                            else None
                        ),
                        staff,
                    )

            # Backdate fixture records consistently.
            Order.objects.filter(pk=order.pk).update(
                created_at=created_at
            )

            events = list(order.status_events.all())

            for step, event in enumerate(events):
                event.recorded_at = created_at + timedelta(
                    minutes=step * 10
                )
                event.save(update_fields=["recorded_at"])

            if stage == "completed":
                finished = events[-1].recorded_at

                Order.objects.filter(pk=order.pk).update(
                    completed_at=finished
                )
                Payment.objects.filter(order=order).update(
                    recorded_at=finished
                )
                StockMovement.objects.filter(
                    allocation__item__order=order
                ).update(recorded_at=finished)

    def allocate_fixture_order(self, order, today, split=False):
        """Include one completed order split across two batches."""
        allocations = []

        for position, item in enumerate(order.items.all()):
            batches = list(
                Batch.objects.filter(
                    medicine=item.medicine,
                    expiry_date__gt=today,
                    quantity_available__gte=item.quantity,
                )[:2]
            )

            if split and position == 0:
                for batch, quantity in zip(
                    batches,
                    (1, item.quantity - 1),
                ):
                    allocations.append(
                        {
                            "item": item,
                            "batch": batch,
                            "quantity": quantity,
                        }
                    )
            else:
                allocations.append(
                    {
                        "item": item,
                        "batch": batches[0],
                        "quantity": item.quantity,
                    }
                )

        return allocations

    def make_prescription(
        self,
        customer,
        staff,
        status,
        created_at,
        saved_files,
    ):
        prescription = Prescription(
            customer=customer,
            status=status,
            uploaded_at=created_at - timedelta(hours=1),
        )

        if status != "pending":
            prescription.reviewed_by = staff
            prescription.reviewed_at = (
                created_at - timedelta(minutes=20)
            )

        if status == "rejected":
            prescription.rejection_reason = (
                "Document details are not legible; "
                "request a clear replacement."
            )

        prescription.document.save(
            "training.pdf",
            ContentFile(
                create_demo_pdf(
                    "Workflow review",
                    customer_name=customer.get_full_name(),
                )
            ),
            save=False,
        )

        saved_files.append(
            (
                prescription.document.storage,
                prescription.document.name,
            )
        )

        prescription.full_clean()
        prescription.save()

        return prescription