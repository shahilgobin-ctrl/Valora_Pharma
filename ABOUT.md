# About and Contact pages

This contribution provides `/about/` and `/contact/` in the existing Django
project. Both pages extend `frontend/templates/pages/base.html`, use semantic
HTML and keep all CSS inside one `<style>` in the document head. Fonts, images
and icons are embedded; these pages need no external assets or JavaScript.

## Run locally

1. Pull or download the `About-page` branch into your own project folder.
2. On Windows, run `run_windows.bat`. On macOS/Linux, run `bash run.sh`.
3. Open **http://127.0.0.1:8000/about/** or **http://127.0.0.1:8000/contact/**.

The existing launcher installs dependencies and applies migrations, including
the new ContactMessage table. Keep any existing database whose data you need.
For an already configured environment:

```sh
python backend/manage.py migrate
python backend/manage.py runserver
```

For a preview without a server, open `frontend/about-preview.html` or
`frontend/contact-preview.html`. They link to each other. Account links and
Contact submission are inactive in the static previews; test those in Django.

## Figma reference

| Page | Source node | Native comparison viewport |
| --- | --- | --- |
| [About](https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=62-9) | `62:9` | 1265 × 1014 px |
| [Contact](https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=137-323) | `137:323` | 1579 × 1224 px |

The original assets, text, fonts, colours and geometry are retained. Compare at
100% browser zoom. Responsive layouts cover widths down to 320 px. Browser font
rasterisation can differ from Figma exports; identical pixels across browsers
are not claimed. The two Figma frames themselves use different header styles
and fonts. Poppins, Inter and Plus Jakarta Sans are embedded as WOFF fonts with
their full SIL Open Font Licenses retained in templates and previews.

## Behaviour

- About, Contact, Sign in and Register use named Django routes.
- Home, Products/Shop and Cart become links when the integrated project exposes
  `home`, `shop:shop` and `shop:cart`. Without those routes they are inactive.
- Contact validates five fields on the server; phone is optional. A valid
  submission saves a ContactMessage and redirects to a confirmation. Refresh
  after the redirect does not resubmit the message.
- The form has CSRF protection, escaped output, field errors, labels and keyboard
  focus. Saved messages are available in Django administration to users with the
  relevant model permissions. There is no public list of messages.
- Contact submission stores a message in the database. It sends no email or SMS.

The pharmacy services, certifications, address and contact details reproduce the
supplied design concept. This contribution does not independently verify those
claims or implement every service described. The original orange/white colours
are retained for fidelity; this is not an accessibility conformance certification.

## Contribution files

| File | Purpose |
| --- | --- |
| `frontend/templates/pages/base.html` | Shared document, internal CSS and navigation |
| `frontend/templates/pages/about.html` | About design and embedded assets |
| `frontend/templates/pages/contact.html` | Contact design and bound form |
| `backend/pages/views.py` | Original About view, preserved |
| `backend/pages/contact_views.py` | Contact GET/POST handling |
| `backend/pages/urls.py` | Named page routes |
| `backend/pages/forms.py` | Contact validation |
| `backend/pages/models.py` | Contact message persistence |
| `backend/pages/admin.py` | Permission-protected message administration |
| `backend/pages/migrations/0001_initial.py` | Contact table migration |
| `backend/pages/tests.py` | 22 page, navigation and submission tests |
| `export_about_preview.py` | Generates both standalone previews |

After editing templates, run `python export_about_preview.py`.

## Verification

Checked on 30 October 2026 with Python 3.12, Django 5.2.17 and Chromium
134.0.6998.35 on Linux:

```sh
python backend/manage.py check
python backend/manage.py makemigrations --check --dry-run
python backend/manage.py test accounts pages
```

All **42 tests passed**: 20 existing account tests and 22 page/form tests.
Browser checks cover both pages at 320, 390, 600, 768, 1024, 1100, 1264, 1265,
1440 and 1579 px, including overflow, embedded assets and active navigation.
Nine interaction checks cover page navigation, account links, keyboard access,
Contact submission and linked static previews. The existing Windows launcher
was not executed in this Linux environment.

See [ABOUT_CONTACT_INTEGRATION.md](ABOUT_CONTACT_INTEGRATION.md) for the exact
teammate revisions tested, template differences and unresolved integration work.
