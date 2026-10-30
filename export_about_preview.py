"""Export both page designs as linked, self-contained HTML previews."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.template.loader import render_to_string
from pages.forms import ContactForm

for page in ("about", "contact"):
    context = {"active_page": page, "preview_mode": True}
    if page == "contact":
        context["form"] = ContactForm()
    output = ROOT / "frontend" / f"{page}-preview.html"
    html = render_to_string(f"pages/{page}.html", context)
    output.write_text("\n".join(line.rstrip() for line in html.splitlines()).rstrip() + "\n", encoding="utf-8")
    print(f"Created {output}")
