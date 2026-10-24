from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from prescriptions.models import Prescription


def create_demo_pdf(scenario):
    """Build a small, valid PDF using only Python's standard library."""

    lines = [
        "VALORA PHARMA - UNIVERSITY DEMONSTRATION",
        "FICTIONAL DOCUMENT - NOT A VALID PRESCRIPTION",
        "",
        "Customer: Demo Customer",
        f"Test scenario: {scenario}",
        "",
        "This file is only for testing the review workflow.",
        "It contains no medical instructions.",
        "Do not use it to dispense medicines.",
    ]

    text_commands = [
        "BT",
        "/F1 12 Tf",
        "50 790 Td",
        "20 TL",
    ]

    for index, line in enumerate(lines):
        escaped_line = (
            line.replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
        )
        if index:
            text_commands.append("T*")
        text_commands.append(f"({escaped_line}) Tj")

    text_commands.append("ET")
    stream = "\n".join(text_commands).encode("ascii")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 4 0 R >> >> "
            b"/Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        ),
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]

    for number, content in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode("ascii"))
        pdf.extend(content)
        pdf.extend(b"\nendobj\n")

    # PDF readers use this table to locate each object.
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")

    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    pdf.extend(
        (
            f"trailer\n"
            f"<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n"
            f"%%EOF\n"
        ).encode("ascii")
    )

    return bytes(pdf)


class Command(BaseCommand):
    help = "Create two fictional prescriptions for local workflow testing."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "Demo prescriptions can only be created with DEBUG=True."
            )

        if not settings.MEDIA_ROOT:
            raise CommandError(
                "Configure MEDIA_ROOT before running this command."
            )

        user_model = get_user_model()
        saved_files = []
        created_prescriptions = []

        try:
            with transaction.atomic():
                customer, created = user_model.objects.get_or_create(
                    email="prescription-demo@example.invalid",
                    defaults={
                        "first_name": "Demo",
                        "last_name": "Customer",
                        "account_type": "customer",
                        "is_active": False,
                        "is_staff": False,
                        "is_superuser": False,
                    },
                )

                if created:
                    # Demo records do not need a usable login account.
                    customer.set_unusable_password()
                    customer.save(update_fields=["password"])

                if customer.account_type != "customer":
                    raise CommandError(
                        "The demo email belongs to a non-customer account."
                    )

                # Re-running the command must not reset review decisions.
                if Prescription.objects.filter(
                    customer=customer
                ).exists():
                    self.stdout.write(
                        self.style.WARNING(
                            "Demo prescriptions already exist. "
                            "Their files and review decisions were preserved."
                        )
                    )
                    return

                scenarios = [
                    ("approval", "Approval workflow"),
                    ("rejection", "Rejection workflow"),
                ]

                for filename, scenario in scenarios:
                    prescription = Prescription(customer=customer)

                    prescription.document.save(
                        f"demo-{filename}.pdf",
                        ContentFile(create_demo_pdf(scenario)),
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
                    created_prescriptions.append(
                        (prescription.pk, scenario)
                    )

        except Exception:
            # Database rollback does not remove files from storage.
            for storage, name in saved_files:
                storage.delete(name)
            raise

        self.stdout.write(
            self.style.SUCCESS(
                "Created two fictional pending prescriptions."
            )
        )

        for prescription_id, scenario in created_prescriptions:
            self.stdout.write(
                f"{scenario}: "
                f"http://127.0.0.1:8000/pharmacist/"
                f"prescriptions/{prescription_id}/"
            )