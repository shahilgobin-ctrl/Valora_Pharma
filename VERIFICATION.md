# Combined verification

The integrated project includes Home, Shop, About, Contact, pharmacist,
manager and administrator workspaces. All account roles use the shared login.
Customer registration creates an active account and returns to sign in;
customer email verification routes have been removed. Password recovery
remains available through email codes.

The login merge preserves customer redirects to Home, safe return links,
pharmacist and manager dashboard redirects, administrator access restrictions,
POST logout and the disabled manager preview bypass.

Merge validation: all 321 combined tests passed, Django checks found no issues,
and migration model checks found no changes. The configured local database had
no pending migrations. No migrations were applied during this merge.

Validation commands, using the project virtual environment:

```powershell
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend/manage.py migrate --plan
Push-Location backend
..\.venv\Scripts\python.exe manage.py test --noinput
Pop-Location
```

Migration plans describe the configured local database. This merge does not
apply migrations to that database. In particular, review accounts.0005 before
applying it: it removes verification metadata and activates earlier pending
customer signups. Preserve database and private upload backups before any
upgrade. Existing migration history is retained.

Browser review remains necessary for responsive layouts, navigation, shared
login and logout, role dashboards, and password recovery. Real SMTP delivery
and real payments are not verified; checkout uses simulated payment.
