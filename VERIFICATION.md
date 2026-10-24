# Verification — 24 October 2026

- Django 5.2.17, SQLite, Python 3.12.
- System check: no issues.
- 101 tests passed (accounts, prescriptions, pharmacist, inventory, orders).
- Fresh database migrations applied successfully.
- `makemigrations --check --dry-run`: no changes detected.
- New JavaScript passed `node --check`.
- Demo command created fictional OTC and prescription online orders.
- Automated end-to-end HTTP test creates a walk-in draft, saves batch allocations,
  records payment, completes the order and renders the receipt.
- Rollback, repeated submission/completion, insufficient stock/cash, expiry,
  split batches, prescription ownership, status order and permission checks pass.
- Existing accounts and prescription migration files are unchanged.

## Verification limits

Browser visual/interaction verification was not completed: Chromium download
failed in this environment. Check desktop/mobile layout and native PDF display
locally. No real payment gateway, production deployment or concurrency load test
was performed. Do not interpret passing tests as production certification.

## Package contents

Source, static assets, migrations, tests and setup guides only. No local database,
user uploads, secret keys, virtual environment or Git history are included.
