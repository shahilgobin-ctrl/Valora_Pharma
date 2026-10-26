"""Generate clearly labelled fictional training documents."""


def create_demo_pdf(
    scenario,
    customer_name="Fictional customer",
):
    """Build a small valid PDF using Python's standard library."""

    lines = [
        "VALORA PHARMA - UNIVERSITY DEMONSTRATION",
        "FICTIONAL DOCUMENT - NOT A VALID PRESCRIPTION",
        "",
        f"Customer: {customer_name}",
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

    stream = "\n".join(text_commands).encode(
        "ascii",
        errors="replace",
    )

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 4 0 R >> >> "
            b"/Contents 5 0 R >>"
        ),
        (
            b"<< /Type /Font /Subtype /Type1 "
            b"/BaseFont /Helvetica >>"
        ),
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

    xref_offset = len(pdf)

    pdf.extend(
        f"xref\n0 {len(offsets)}\n".encode("ascii")
    )
    pdf.extend(b"0000000000 65535 f \n")

    for offset in offsets[1:]:
        pdf.extend(
            f"{offset:010d} 00000 n \n".encode("ascii")
        )

    pdf.extend(
        (
            f"trailer\n"
            f"<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n"
            f"{xref_offset}\n"
            f"%%EOF\n"
        ).encode("ascii")
    )

    return bytes(pdf)