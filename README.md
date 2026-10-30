# Valora Pharma

Django pharmacy project with public Home, Shop, About and Contact pages; shared login, direct customer registration and password recovery; and protected pharmacist, pharmacy manager and administrator workspaces.

Inventory medicines, batch stock, prices, selling units and prescription flags are authoritative across the public shop and pharmacist workspace. Checkout records a simulated online payment once in the shared order system. Pharmacist fulfilment reuses it and deducts batch stock at completion. Delivery uses the configured shop fee; pickup has no fee. No real payment is processed.

See [HOME_INTEGRATION.md](HOME_INTEGRATION.md) for migration and integration notes and [backend/shop/README.md](backend/shop/README.md) for the shared data model.

The existing showcase database and uploads must be preserved. The Admin and Manager migrations in this branch are pending review and have not been applied to the existing database. The convenience starters below apply migrations automatically. While migration review is pending, do not run those starters. After reviewing and backing up the configured database and private uploads, apply the approved migrations explicitly; never reset or reseed the showcase data.

## Start on Windows

1. Install **Python 3.10 through 3.14** from [python.org](https://www.python.org/downloads/). A recent Python 3.12 or 3.13 release is a good choice. Enable the Python launcher during installation.
2. Extract the ZIP completely into a folder.
3. Double-click **`run_windows.bat`**.
4. Wait for the dependencies and database to finish preparing, then open **http://127.0.0.1:8000/login/**.

The first run needs an internet connection to download dependencies. The starter creates a project-local `.venv`, installs `requirements.txt`, applies database migrations and starts the development server. Later runs reuse that environment and your database. Keep the console window open; press **Ctrl+C** to stop.

You can also open PowerShell in the extracted project folder and run:

```powershell
.\run_windows.bat
```

For a different local port:

```powershell
.\run_windows.bat -Address 127.0.0.1:8001
```

The batch file runs `start.ps1` with a temporary, process-only execution-policy setting. It does not change your system's PowerShell policy. The starter checks `py`, then `python3`, then `python` for an installed, supported runtime. If `py` says there is no runtime installed, install Python itself using the link above.

## Start on macOS or Linux

Install Python 3.10 through 3.14, extract the ZIP, open a terminal in the project folder and run:

```bash
bash run.sh
```

For a different local port, use `bash run.sh 127.0.0.1:8001`. On Linux, your distribution may require its `python3-venv` package before creating a virtual environment.

## Pages

| Page | Local URL |
| --- | --- |
| Public Home | http://127.0.0.1:8000/ |
| Shop | http://127.0.0.1:8000/shop/ |
| Cart | http://127.0.0.1:8000/cart/ |
| About | http://127.0.0.1:8000/about/ |
| Contact | http://127.0.0.1:8000/contact/ |
| Pharmacy Manager | http://127.0.0.1:8000/manager/ |
| Super Administrator | http://127.0.0.1:8000/superadmin/ |
| Pharmacist workspace | http://127.0.0.1:8000/pharmacist/ |
| Shared login for all roles | http://127.0.0.1:8000/login/ |
| Customer landing page (temporary) | http://127.0.0.1:8000/account/customer/ |
| Staff landing page (temporary) | http://127.0.0.1:8000/account/staff/ |
| Supplier landing page (temporary) | http://127.0.0.1:8000/account/supplier/ |
| Administrator compatibility route (redirects to workspace) | http://127.0.0.1:8000/account/admin/ |
| Customer registration | http://127.0.0.1:8000/register/ |
| Shared password recovery | http://127.0.0.1:8000/password/forgot/ |
| Terms and Conditions (draft) | http://127.0.0.1:8000/terms/ |
| Django administration | http://127.0.0.1:8000/admin/ |

Active staff in the Pharmacist group reach the pharmacist dashboard. Active staff with the Pharmacy Managers permission reach the manager dashboard. Active administrator superusers reach the administrator workspace. The administrator workspace can manage accounts, roles, audit logs and registration settings; public staff registration stays closed. Customers default to Home and retain safe return-to-Shop/cart destinations. Older `/staff/login/` bookmarks redirect to `/login/`. Login uses email and password. Registration collects first name, last name, username, date of birth through a calendar picker, gender, email, phone number and password, and requires agreement to the linked Terms and Conditions. The acceptance time and terms version are saved with the account. Passwords must contain at least eight characters, cannot be entirely numeric or commonly used, and cannot closely resemble the account details. Duplicate emails and usernames are rejected case-insensitively. Existing accounts may have no username.

The Terms and Conditions page contains **draft example text**. Replace it with your team's approved terms before launching the site; update `TERMS_VERSION` in `backend/accounts/models.py` when the text changes.

Customer registration creates an active account and sends the customer to sign in without an email code. Public employee and supplier registration is closed: `/staff/register/` returns 403. A superuser provisions employee and supplier accounts in `/superadmin/` or Django administration at `/admin/`; those accounts start inactive until that superuser verifies the person's identity and activates them. Employees and suppliers then use `/login/`. Each destination checks the role again on every request. A pharmacy employee account does not receive Django administration access merely by having the pharmacy `staff` role.

Passwords are stored using Django's password hashing. Forms include CSRF protection and server-side validation. Login failures are limited per email-and-IP pair to eight attempts per fifteen minutes, so one user's mistakes do not lock everyone sharing a network. Password recovery requests have per-address cooldown and hourly limits. The development limiter uses a per-process cache.

## Password recovery and email

From the shared sign-in page, select **Forgot password?**, enter the account email, enter the six-digit code, then set a new password. Codes expire after ten minutes, allow five verification attempts, and cannot be reused after the password changes. The request page shows the same response for unknown addresses. Recovery is available only for active accounts.

In local development, Django prints password reset emails in the **server terminal**. For delivery to an inbox, configure your email provider through the `DJANGO_EMAIL_*` settings below before starting Django. Never commit SMTP credentials. A production SMTP setup requires a sender address and email host. The project needs a shared cache when run with multiple workers for request limits; see the configuration section.

## Create an administrator and employee accounts

After the first startup, open a second PowerShell window in the project folder:

```powershell
.\.venv\Scripts\Activate.ps1
python backend/manage.py createsuperuser
```

If PowerShell blocks activation, use the environment's interpreter directly:

```powershell
.\.venv\Scripts\python.exe backend/manage.py createsuperuser
```

On macOS or Linux:

```bash
source .venv/bin/activate
python backend/manage.py createsuperuser
```

Open `/admin/`, sign in with that superuser, open **Users**, and select **Add user**. Set **Account type** to **Staff** or **Supplier** and enter an initial password. New privileged accounts start **inactive**. After checking the person's identity, edit the account and enable **Active**. Do not grant Django **Staff status** or **Superuser status** to ordinary pharmacy employees or suppliers. Give the initial password securely, then have them change it using **Forgot password?** once email delivery is configured. Custom administrator accounts are created with `createsuperuser`; they receive the `admin` pharmacy role. `/admin/` is Django's account-management site, while `/account/admin/` is a temporary destination for the teammate's custom admin pages.

## Optional development account

Accounts are not created automatically. You can register through the pages or explicitly create a development-only sample customer:

```powershell
.\.venv\Scripts\python.exe backend/manage.py seed_demo
```

On macOS/Linux, use `.venv/bin/python backend/manage.py seed_demo`.

The command uses `demo.customer@example.test` and prints a new random password **once** in the terminal. It never resets or edits an existing account, and the login page never displays demo credentials. The command runs only with `DJANGO_DEBUG=true`.

## Folder layout

```text
pharmacy-auth/
├── backend/             Django project, accounts, migrations and tests
│   ├── manage.py
│   └── db.sqlite3       Created after the first migration
├── frontend/
│   ├── templates/       Login, registration, recovery, landing and terms HTML
│   └── static/          Styles, scripts and design assets
├── requirements.txt     Pinned Python dependency
├── .env.example         Environment-variable reference
├── TEAM_INTEGRATION.md  Shared roles, URL mapping, and collaborator guidance
├── start.ps1            Windows PowerShell starter
├── run_windows.bat      Windows double-click starter
└── run.sh               macOS/Linux starter
```

There is no separate Node.js build step. Django serves the frontend templates and static files locally. SQLite stores accounts in `backend/db.sqlite3`; keep that file to retain your local users.

## Manual setup and checks

If you prefer manual setup, run the following in PowerShell from the project folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python backend/manage.py migrate
python backend/manage.py runserver
```

After activation, `python` refers to the virtual environment, even if `python` was unavailable before setup. If activation is blocked, substitute `.\.venv\Scripts\python.exe` for `python` in the remaining commands.

For macOS/Linux, substitute `python3 -m venv .venv` and `source .venv/bin/activate` for the first two commands.

Run Django's system check and the included backend tests with:

```powershell
python backend/manage.py check
python backend/manage.py test accounts
```

## Configuration and deployment

Local development works with the default settings. **`.env.example` is a configuration reference; neither Django nor the starter scripts automatically load `.env` files.** Set variables in the current terminal or through your hosting service. For example, in PowerShell:

```powershell
$env:DJANGO_DEBUG = "false"
$env:DJANGO_SECRET_KEY = "your-long-random-private-secret"
$env:DJANGO_ALLOWED_HOSTS = "your-pharmacy.example"
$env:DJANGO_CSRF_TRUSTED_ORIGINS = "https://your-pharmacy.example"
```

On macOS/Linux, use `export DJANGO_DEBUG=false`, and similarly export the other values.

| Variable | Development default / purpose |
| --- | --- |
| `DJANGO_DEBUG` | `true`; use `false` for production |
| `DJANGO_SECRET_KEY` | Generated locally in `backend/.dev-secret-key`; supply a private, unique value in production |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]`; provide your domain in production |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Optional comma-separated HTTPS origins |
| `DJANGO_DATABASE_PATH` | Optional database location; otherwise `backend/db.sqlite3` |
| `DJANGO_SECURE_SSL_REDIRECT` | `false` in development, `true` in production |
| `DJANGO_CACHE_BACKEND` | `django.core.cache.backends.locmem.LocMemCache`; choose a shared cache for multiple server workers |
| `DJANGO_CACHE_LOCATION` | `pharmacy-auth`; the cache location or table name required by the selected backend |
| `DJANGO_EMAIL_BACKEND` | Console in development; SMTP in production for verification and recovery |
| `DJANGO_DEFAULT_FROM_EMAIL` | Sender address; required in production |
| `DJANGO_EMAIL_HOST` / `DJANGO_EMAIL_PORT` | SMTP server and port (default port `587`) |
| `DJANGO_EMAIL_HOST_USER` / `DJANGO_EMAIL_HOST_PASSWORD` | SMTP credentials |
| `DJANGO_EMAIL_USE_TLS` / `DJANGO_EMAIL_USE_SSL` | SMTP transport security (`true` / `false` by default) |

For Django's built-in shared database cache, set `DJANGO_CACHE_BACKEND=django.core.cache.backends.db.DatabaseCache` and `DJANGO_CACHE_LOCATION=pharmacy_auth_cache`, then run `python backend/manage.py createcachetable` after applying migrations. All server workers must use the same database and cache configuration.

Before deployment, use a production WSGI/ASGI server and HTTPS, run `python backend/manage.py collectstatic`, run `python backend/manage.py check --deploy` with the production settings, configure a shared cache for the login and password recovery limits, verify SMTP delivery to a real inbox, and plan database backups. The included starters run Django's local development server. See Django's [deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/) for hosting configuration.

The project uses **Django 5.2.17 LTS**, the latest 5.2 patch listed on the [official downloads page](https://www.djangoproject.com/download/) when this package was prepared. Django 5.2 supports [Python 3.10–3.14](https://docs.djangoproject.com/en/5.2/releases/5.2/).

## Design source

- [Registration reference — node 187:675](https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=187-675&m=dev)
- [Customer login reference — node 49:76](https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=49-76&m=dev)
- [Earlier staff-specific reference — node 187:559](https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=187-559&m=dev)

The requested screens are implemented as responsive pages, with working Django forms and locally bundled frontend assets.


## Pharmacist workflows
`/pharmacist/` is a protected live dashboard. See the implementation guide above.
