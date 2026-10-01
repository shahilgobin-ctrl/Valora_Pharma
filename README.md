# Valora Pharma - Super Administrator

A functional Django administration module for FR-29 (customer/staff account management) and FR-30 (staff roles and permissions). Work is on the `admin` branch. The Django/accounts foundation was copied using read-only Git access to `origin/pharmacy-login-register`; no branches were merged or switched.

## Run locally

Python and Django are already available in the current workspace environment. From the project root:

```powershell
python backend/manage.py migrate
python backend/manage.py createsuperuser
python backend/manage.py runserver
```

Choose your own administrator email and password when prompted. Then open **http://127.0.0.1:8000/superadmin/**. Sign in with that account. The database starts without sample users; dashboard counts and lists reflect actual records.

For a fresh environment:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe backend/manage.py migrate
.\.venv\Scripts\python.exe backend/manage.py createsuperuser
.\.venv\Scripts\python.exe backend/manage.py runserver
```

`run_windows.bat` (or `bash run.sh` on macOS/Linux) creates an environment, installs dependencies, applies migrations and starts the server. Create your administrator in a second terminal using that environment's Python. `.env.example` is a reference; environment files are not loaded automatically.

The dependency pin in `requirements.txt` is inherited from the authentication branch. Local verification used the installed Python 3.11.4 / Django 5.2 environment. Package-index access was unavailable during implementation, so the pinned fresh-install environment was not verified.

## Navigation and functionality

The same sidebar appears on every administrator page, including Roles & Permissions, in this order:

1. **Overview** - live total, active, inactive and staff counts; linked account list.
2. **User Management** - search/filter, view details, create and update accounts, set/reset passwords, activate/deactivate accounts, assign customer/pharmacist/manager/administrator roles.
3. **Roles & Permissions** - four cards following the supplied reference; edit each operational role's permissions. Changes apply to its members. Super Administrator always has full access.
4. **Audit Log** - timestamp, actor, action, target and IP; change details, search/filter, pagination and CSV export of all matching events.
5. **System Settings** - portal name, support email, rows per page, customer and staff registration switches. All settings persist and affect the application.
6. **Sign Out** - CSRF-protected POST, audit event and session logout.

The four supplied images guided the layouts, colours, table structure and whitespace. System Settings uses the same typography, teal accents and sidebar. Browser screenshot verification could not run because no browser was available to the connected UI tool; template rendering and workflows were verified through Django tests.

Account names open the detail page, which has an **Edit account** button. Role dropdowns have an explicit **Save** action. Deactivation and role changes ask for confirmation in the browser. Administrators cannot deactivate or demote themselves. Edit profile allows changing your own password while preserving your current session.

## Architecture and integration

- `backend/accounts/`: existing email-based `accounts.User`, customer/staff authentication and validation.
- `backend/config/`: shared project configuration. `/` redirects to the new portal; Django's built-in administration remains at `/admin/`.
- `backend/superadmin/`: forms, access checks, account/role workflows, audit service, settings and tests.
- `frontend/templates/superadmin/`: Django-rendered pages with a shared sidebar.
- `frontend/static/superadmin/`: custom responsive CSS, local Poppins fonts and small confirmation script. No Node build or external font request is needed for the administrator pages.
- SQLite defaults to `backend/db.sqlite3`. `DJANGO_DATABASE_PATH` can select a different SQLite file.

Migrations preserve the existing `accounts.User` model and create `Role`, `AuditLog` and `SystemSettings`. Roles use Django `Group` and `Permission`; no parallel authentication system is introduced. Public customers receive the Customer group. Public staff registrations remain inactive and unassigned until an administrator assigns their role and activates the account.

`account_type="staff"` represents a pharmacy employee; it does not grant administration access. Portal access requires an active `is_superuser` account. The administration workflow sets Django `is_staff` only for Super Administrators. Operational role permissions cannot grant governance access. Moving between roles replaces the managed role group; unrelated groups/direct permissions are preserved for compatibility.

The catalogue, prescriptions, POS, stock and reporting permission names are persisted permission definitions matching the reference. Those business modules are not implemented on this branch. Their future views must enforce permissions with checks such as:

```python
request.user.has_perm("superadmin.approve_prescriptions")
request.user.has_perm("superadmin.adjust_stock")
```

No customer shop or pharmacy manager branch was imported. Future integration should keep this user model, add business apps to the shared settings/URLs and enforce the appropriate permission codenames.

Audit events cover changes made through this portal plus administrator sign-in/sign-out. Account, role and settings changes are committed with their audit records in the same transaction. Password values are never recorded. The portal provides no audit edit/delete endpoint. Changes made directly in a shell or Django's separate built-in admin are outside this portal's audit service. Future modules can call `superadmin.services.audit(request, action, target, details)` within their write transaction.

CSV export neutralizes spreadsheet formulas. Timestamps use `Indian/Mauritius`. The IP field records the direct connection address, not untrusted forwarded headers.

## Optional reference data

Only for local development, set `VALORA_DEMO_PASSWORD` to a strong password of your choice in your terminal, then run:

```powershell
python backend/manage.py seed_admin_demo
```

This creates `admin@valora.mu` plus the six reference customer/staff accounts, all using the password you supplied. It refuses to run outside DEBUG or if any demo email already exists. It never runs automatically. The overview includes the administrator, so these records produce seven total users.

The implementation's isolated `.qa/preview.sqlite3` database is ignored by Git and is separate from the normal application database. It is only test data.

## Verification

Run these from the repository root (use the explicit app labels for test discovery):

```powershell
python backend/manage.py check
python backend/manage.py makemigrations --check --dry-run
python backend/manage.py test accounts superadmin
```

Coverage includes the inherited authentication tests plus administrator-only access, account CRUD, role assignment and effective permissions, self-lockout prevention, activation, password/session handling, settings/registration integration, audit transaction rollback, CSV export, filtering, CSRF, POST-only mutations and logout.

Local development defaults to DEBUG and an in-process login limiter. Deployment needs a configured secret, allowed hosts, HTTPS, shared cache, database backups and a production WSGI/ASGI server. See `.env.example` and `backend/config/settings.py` for the available settings. SQLite is the local default; higher-concurrency production use needs an appropriate database configuration and concurrency testing.
