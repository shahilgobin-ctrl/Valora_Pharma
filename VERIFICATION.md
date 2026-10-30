# Combined verification - 30 October 2026

Home, shop and About-page were integrated in order into merger, preserving the existing pharmacist workspace and shared authentication. Full integration details, source commits and the pending migration plan are in [HOME_INTEGRATION.md](HOME_INTEGRATION.md).

- Full .venv Django suite: 226 tests passed across all seven installed local apps.
- Django check: no issues. makemigrations --check --dry-run: no changes detected.
- Home and Shop JavaScript: node --check passed.
- Fresh test-database migrations and a complete upgrade of a disposable showcase copy passed.
- All original records in the showcase copy were preserved; SQLite integrity passed.
- Existing pharmacist on the migrated copy: active staff, Pharmacist group, dashboard HTTP 200 and correct shared-login redirect.
- The real configured database and 24 private uploads remained byte-for-byte unchanged.

Pending on the real database: orders.0006; shop.0001 through 0007, including both parallel 0004/0005 histories; and pages.0001. No migrations were applied to the real database and nothing was reset or reseeded. No migration history was deleted.

Browser layouts and interaction still require combined review. Real SMTP and real payments were not tested; checkout uses a clearly labelled simulation. No push or deployment was performed.
