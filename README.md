# Valora Pharma

Valora Pharma is a Django pharmacy application with public Home, Shop, About
and Contact pages, customer accounts, and protected pharmacist, pharmacy
manager and administrator workspaces.

The project uses Django 5.2.17, SQLite for local development, Django templates,
and locally bundled CSS and JavaScript. There is no Node.js build step.

## Features

- Customers can browse medicines, manage a cart, submit prescriptions and
  place orders with simulated online payment.
- Pharmacists can review prescriptions, process online orders, record walk-in
  sales, allocate batches and issue receipts.
- Pharmacy managers can manage medicines, batches, suppliers, purchase orders,
  stock receipts, adjustments, expiry alerts and reports.
- Administrators can manage accounts, assign roles, review audit logs and
  control customer registration.
- Shared authentication includes email verification, password recovery,
  server-side validation, CSRF protection and request limits.

## Shared inventory and payments

`inventory.Medicine` owns medicine information, selling prices, selling units,
prescription requirements and reorder levels. `inventory.Batch` owns physical
stock and expiry dates. Manager, shop and pharmacist workflows share these
records. `shop.Product` links explicitly to a medicine and provides storefront
information such as artwork and category placement.

Shop availability excludes expired batches and accounts for pending online
orders. Checkout records one simulated payment in the shared order system;
pharmacist completion reuses that payment and deducts the allocated batch stock.
Prescription approval and stock validation remain required before fulfilment.
Pickup has no delivery fee; delivery uses the configured shop fee. No real
payment is processed.

## Run an existing installation

From the project root, start Django with the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe backend/manage.py runserver
```

On macOS or Linux:

```bash
.venv/bin/python backend/manage.py runserver
```

Open http://127.0.0.1:8000/. Keep the terminal open and press `Ctrl+C` to stop.
To use another port, append `127.0.0.1:8001` to the command.

## First-time setup

Install Python 3.10 through 3.14. The integrated project was verified using
Python 3.12. From the project root on Windows:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe backend/manage.py migrate
.\.venv\Scripts\python.exe backend/manage.py createsuperuser
.\.venv\Scripts\python.exe backend/manage.py runserver
```

On macOS or Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python backend/manage.py migrate
.venv/bin/python backend/manage.py createsuperuser
.venv/bin/python backend/manage.py runserver
```

The convenience launchers `run_windows.bat` and `run.sh` create or reuse `.venv`,
install dependencies, apply migrations automatically and start the development
server. Use them only after reviewing migrations for any database you need to
preserve. The direct server command above does not apply migrations.

## Database, uploads and upgrades

The default database is `backend/db.sqlite3`. Private uploaded documents are
stored in `backend/private_uploads` and served through permission-checked views.
Preserve both when moving or backing up an installation. Database files,
uploads, local secrets and passwords must not be committed to Git.

Before upgrading an existing installation, stop the development server, create
and verify backups outside the repository, and inspect the migration plan:

```powershell
.\.venv\Scripts\python.exe backend/manage.py migrate --plan
.\.venv\Scripts\python.exe backend/manage.py makemigrations --check --dry-run
```

Apply reviewed migrations with `migrate`, then run `check`. Do not reset or
reseed an existing database or delete migration history.

The nine integration migrations were applied to the local showcase database on
30 October 2026. Verification confirmed database integrity, preserved existing
business records and accounts, checked all 52 batch links, and verified 24
prescription uploads. No migrations remained pending afterward. This describes
that local installation; each checkout must inspect its own migration state.

## Pages and access

Paths below use http://127.0.0.1:8000 as the local base URL.

| Page | Path | Access |
| --- | --- | --- |
| Home | `/` | Public |
| Shop | `/shop/` | Public browsing |
| Cart | `/cart/` | Customer workflow |
| About | `/about/` | Public |
| Contact | `/contact/` | Public; submissions are stored, not emailed |
| Shared login | `/login/` | All account roles |
| Customer registration | `/register/` | When enabled by an administrator |
| Email verification | `/email/verify/` | Customer verification |
| Resend verification code | `/email/resend/` | Customer verification |
| Password recovery | `/password/forgot/` | Active accounts |
| Pharmacist workspace | `/pharmacist/` | Active staff in the Pharmacist group |
| Manager workspace | `/manager/` | Authorized active staff or administrators |
| Administrator workspace | `/superadmin/` | Active administrator superusers |
| Django administration | `/admin/` | Authorized Django administrators |
| Terms | `/terms/` | Public; draft text |

After shared login, pharmacists reach their dashboard, authorized managers
reach the manager dashboard, and administrator superusers reach the
administrator workspace. Customers default to Home and retain approved local
return destinations. If staff belong to both operational groups, the pharmacist
dashboard takes priority. Access is checked on each protected request.

Older `/staff/login/` bookmarks redirect to shared login. `/account/admin/`
redirects to the administrator workspace. Ordinary staff and supplier landing
routes remain available for accounts without an operational dashboard role.

## Accounts and email

Customer registration creates an inactive account and sends a six-digit email
verification code. Codes expire after 15 minutes and allow five attempts.
Password recovery codes expire after ten minutes and allow five attempts.
Passwords are stored using Django password hashing.

Public staff registration is closed. Use `/superadmin/` to create accounts and
assign Customer, Pharmacist, Pharmacy Manager or Super Administrator roles.
Use Django administration for supplier accounts and other account settings.
Review activation explicitly when provisioning accounts. Ordinary pharmacy
staff do not need Django staff or superuser flags. Existing accounts and
passwords are retained during upgrades.

In development, verification and recovery emails appear in the server terminal.
Configure SMTP to deliver them to an inbox. Never include credentials in the
README or commit them to the repository.

The Terms and Conditions page contains draft example text. Replace it with
approved terms before launch and update `TERMS_VERSION` when the terms change.

## Checks and tests

Use the project's virtual environment. Run test discovery from `backend` so
the full installed-app suite is discovered:

```powershell
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend/manage.py migrate --plan
Push-Location backend
..\.venv\Scripts\python.exe manage.py test --noinput
Pop-Location
```

On macOS or Linux, run the equivalent checks with `.venv/bin/python`, then
`cd backend` and run `../.venv/bin/python manage.py test --noinput`.

The combined integration suite passed 324 tests. It covers accounts, inventory,
prescriptions, orders, pharmacist, shop, public pages, manager and administrator
workflows. Fresh migrations and upgrading a disposable copy of the existing
database were also verified. Django tests use a separate test database.

Browser verification should cover responsive layouts, navigation, login and
logout, prescription document access, checkout and fulfilment, manager stock
and purchasing screens, and administrator account and role management.

## Configuration

`.env.example` documents supported settings. Django and the launchers do not
automatically load `.env` files. Set environment variables in the current
terminal or through the hosting environment.

| Variable | Purpose / development default |
| --- | --- |
| `DJANGO_DEBUG` | `true`; use `false` in production |
| `DJANGO_SECRET_KEY` | Local key in `backend/.dev-secret-key`; provide a private production value |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` in development |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Optional comma-separated trusted HTTPS origins |
| `DJANGO_DATABASE_PATH` | Override `backend/db.sqlite3` |
| `DJANGO_MEDIA_ROOT` | Override `backend/private_uploads` |
| `DJANGO_SECURE_SSL_REDIRECT` | Disabled in development; enabled by default in production |
| `DJANGO_CACHE_BACKEND` | Local memory cache by default; use a shared cache with multiple workers |
| `DJANGO_CACHE_LOCATION` | Cache location; default `pharmacy-auth` |
| `DJANGO_EMAIL_BACKEND` | Console in development; SMTP by default in production |
| `DJANGO_DEFAULT_FROM_EMAIL` | Sender address; required in production |
| `DJANGO_EMAIL_HOST` / `DJANGO_EMAIL_PORT` | SMTP server and port; default port `587` |
| `DJANGO_EMAIL_HOST_USER` / `DJANGO_EMAIL_HOST_PASSWORD` | Private SMTP credentials |
| `DJANGO_EMAIL_USE_TLS` / `DJANGO_EMAIL_USE_SSL` | Mutually exclusive SMTP transport options |

For deployment, use HTTPS and a production WSGI/ASGI server, configure SMTP and
a shared cache, collect static files, run `check --deploy` with production
settings, and establish database and private-upload backups. The included
launchers use Django's development server.

## Project layout and further documentation

```text
Valora_Pharma/
|-- backend/
|   |-- accounts/       Authentication and shared roles
|   |-- inventory/      Authoritative medicines and physical batches
|   |-- prescriptions/  Private documents and clinical review records
|   |-- orders/         Shared orders, allocations, payments and receipts
|   |-- pharmacist/     Pharmacist workspace
|   |-- manager/        Inventory management, suppliers and purchasing
|   |-- superadmin/     Account governance, roles, settings and audit logs
|   |-- shop/           Storefront metadata, cart and checkout endpoints
|   |-- pages/          Home, About and Contact pages
|   `-- config/         Django settings and root URLs
|-- frontend/
|   |-- templates/      Django page templates
|   `-- static/         Styles, scripts, fonts and images
|-- requirements.txt
`-- .env.example
```

- [Team integration notes](TEAM_INTEGRATION.md)
- [Home and shop integration history](HOME_INTEGRATION.md)
- [Shop data model](backend/shop/README.md)
- [Manager integration](backend/manager/README.md)
- [About and Contact design notes](ABOUT.md)

Integration reports describe the state when they were written; use current
checks and the migration plan to establish the state of your installation.
