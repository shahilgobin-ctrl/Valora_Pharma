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
    if page == "about":
        css = (ROOT / "frontend/static/pages/about.css").read_text(encoding="utf-8")
        css = css.replace("../accounts/fonts/", "static/accounts/fonts/")
        html = html.replace('<link rel="stylesheet" href="/static/pages/about.css">', '<style>' + css + '</style>')
    header_css = (ROOT / "frontend/static/public-header.css").read_text(encoding="utf-8")
    header_css = header_css.replace("url('accounts/", "url('static/accounts/")
    html = html.replace('<link rel="stylesheet" href="/static/public-header.css">', '<style>' + header_css + '</style>')
    header_js = (ROOT / "frontend/static/public-header.js").read_text(encoding="utf-8")
    html = html.replace('<script src="/static/public-header.js" defer></script>', '')
    html = html.replace('</body>', '<script>' + header_js + '</script>\n</body>')
    html = html.replace('src="/static/accounts/assets/pill-login.svg"', 'src="static/accounts/assets/pill-login.svg"')
    output.write_text("\n".join(line.rstrip() for line in html.splitlines()).rstrip() + "\n", encoding="utf-8")
    print(f"Created {output}")
