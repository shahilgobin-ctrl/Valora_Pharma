# About Us page

The About page is integrated into the existing Django project at `/about/`.
It follows the supplied design, using semantic HTML and one internal `<style>`
element in the document head. The photograph and fonts are embedded; the About
page needs no separate stylesheet, image, font download or JavaScript.

## Open it on Windows

1. Download or pull the `About-page` branch and open the project folder in VS Code.
2. Run `run_windows.bat`, as described in the main README.
3. Open **http://127.0.0.1:8000/about/** in your browser.

For an immediate preview without Python or a server, open
**`frontend/about-preview.html`** directly in Chrome or Edge. This is a complete,
self-contained HTML file. The Sign in and Register links work in the Django
version; they are inactive in the direct-file preview.

For comparison with the supplied screenshot, use a browser viewport of
**856 × 686 px at 100% zoom**. The page adapts at other sizes. The introduction
stacks below 820 px and the cards stack below 600 px. Font rendering and the
recreated small SVG icons can differ slightly from the original Figma view.

## Edit the page

| File | Purpose |
|---|---|
| `frontend/templates/pages/base.html` | HTML document, internal CSS, embedded fonts and navigation |
| `frontend/templates/pages/about.html` | Company text, embedded photograph and benefit cards |
| `backend/pages/views.py` | Renders the About template |
| `backend/pages/urls.py` | Named `pages:about` route |
| `backend/pages/tests.py` | About page checks |
| `export_about_preview.py` | Rebuilds the direct-file HTML preview |

After editing the templates, regenerate the preview from the repository root:

```powershell
.\.venv\Scripts\python.exe export_about_preview.py
```

The existing account pages and their base template are preserved. Integration
adds `pages.apps.PagesConfig` to the installed apps and includes `pages.urls`.
The root URL still opens the existing login page. No About model or migration is
needed because the content is fixed and does not collect or store input.

## Verification

Checked on 26 October 2026 with Python 3.12 and the repository's Django 5.2.17:

```powershell
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py test accounts pages
```

All **39 tests passed**: 20 existing account tests and 19 About tests.
Chromium checks passed at 1440, 1024, 856, 768, 390 and 320 px, including embedded
resources, keyboard navigation, text resizing and the working account links.
The About page loads with one HTML request and no external page resources.
These checks ran on Linux; the Windows startup instructions use the existing
project launcher.

## Design assets

The embedded photograph is the photo area from the supplied design reference.
Poppins Regular and SemiBold are embedded as WOFF fonts; their full SIL Open
Font License is retained in the base template and exported HTML. The original
orange and teal palette is preserved. White text on the original orange has
2.83:1 contrast and needs review before a public accessibility sign-off.

The page describes the supplied pharmacy concept. Its existing project-scope
note distinguishes planned services from implemented functionality.
