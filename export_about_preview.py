"""Export the About design as one HTML file with embedded resources."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.template.loader import render_to_string

output = ROOT / "frontend" / "about-preview.html"
html = render_to_string("pages/about.html", {"active_page": "about", "preview_mode": True})
output.write_text("\n".join(line.rstrip() for line in html.splitlines()).rstrip() + "\n", encoding="utf-8")
print(f"Created {output}")
