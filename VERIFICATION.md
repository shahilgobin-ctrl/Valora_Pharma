# Combined merge verification - 30 October 2026

The merger branch integrates the pharmacist dashboard, prescription review and private document preview, inventory, order fulfilment, walk-in sales and receipts with shared authentication for customers, staff, suppliers and administrators.

Active staff in the Pharmacist group reach `pharmacist:dashboard` through the shared login and legacy staff login. Other roles retain protected landing pages. Pharmacist access still requires both the staff role and Pharmacist group. Customer browsing redirects remain restricted to allowed internal Home/Shop routes.

Public registration creates inactive customers until email verification succeeds. Privileged accounts remain administrator-managed. Shared password recovery, code expiry and attempt limits, request throttling, CSRF and POST-only logout are retained. The admin change form now accepts the incoming administrator role for superusers while preserving mutually exclusive staff group restrictions.

## Checks performed with the project .venv

- `python backend/manage.py check`: no issues.
- `python backend/manage.py makemigrations --check --dry-run`: no changes detected.
- `python backend/manage.py test accounts pharmacist prescriptions inventory orders --noinput`: 175 tests passed, including five new merge integration regressions. Django created and destroyed a separate test database; fresh migrations succeeded there.
- `showmigrations --plan` and `migrate --plan`: inspected without applying migrations to the showcase database.
- SHA-256 comparison confirmed all 25 existing database/upload files were byte-for-byte unchanged after checks and tests. No seeding commands were run.

## Remaining migration steps

The existing database has accounts.0001 applied. After reviewing the merge, stop the app and back up the existing SQLite database and private uploads, then run `.\.venv\Scripts\python.exe backend/manage.py migrate` to apply accounts.0002, accounts.0003 and accounts.0004. Do not reset or reseed it and do not delete migrations.

0002 adds terms metadata and password reset challenges. 0003 adds email verification and supplier/admin roles and changes existing superusers to the administrator role. Existing non-superuser pharmacists, customer activation states and group memberships are preserved. 0004 adds nullable usernames and a case-insensitive uniqueness constraint; existing accounts do not need usernames. Existing accounts are not forced through new-customer verification. The new account code requires these migrations before normal use of the showcase database.

## Verification limits and deployment

Browser layout, native PDF interaction and real SMTP delivery were not checked in this merge pass. Earlier branch records described browser checks for authentication and a blocked Chromium download for pharmacist screens; these are not new combined visual verification. No production deployment, real payment gateway or concurrency load test was performed.

Development email uses the console; production requires SMTP configuration and a shared cache for multiple workers. Terms text remains a draft. Preserve the configured database and private upload locations. Keep databases, uploads, local secrets, SMTP credentials and virtual environments out of source distributions.
