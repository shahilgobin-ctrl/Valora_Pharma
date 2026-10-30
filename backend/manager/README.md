# Pharmacy Manager

Separate manager implementation on Pharmacy-Manager. The public Home template and assets reuse the Home branch implementation, with routes adapted to this branch. Medicine, category, customer-order and payment data use the existing shop models. Shared login remains available for later integration. This branch includes the shared shop and authentication dependencies needed by the manager.

## Navigation and workflows

- Overview: live stock/sales summaries and six shortcuts, without duplicate action rows or developer notices.
- Medicines: compact catalogue; add/edit/archive/reactivate; medicine details contain batch/expiry, stock and supplier history. Reports are opened from the section or record being reviewed. Inventory rules are not duplicated on the medicine edit form.
- Batches & Expiry: record deliveries or allocate existing unbatched stock, create a new medicine and return to the selected batch, edit metadata/quantities, inspect history and export relevant reports. Select a medicine to edit its reorder level and expiry-warning days in this section. Stock history is a section tab. The old inventory-settings URL redirects here.
- Stock Alerts: out-of-stock, below-reorder, expiring and expired stock; uses each medicine's configured warning period, falling back to the existing InventoryPolicy for older records.
- Suppliers: contacts, supply history, purchasing history, contextual reports and removal. Supplier changes and receipts are taken from actual batch snapshots. Suppliers referenced by batches, orders or historic snapshots are deactivated instead of erasing traceability. Unused suppliers can be deleted after confirmation.
- Purchase Orders: creation, date/status filtering, partial/full receiving, details, cancellation before receipt and purchasing reports.
- Customer Orders: read-only oversight and sales reports. Pharmacist approval, dispensing and pickup-status actions remain outside manager authority under the assignment.

## Stock integrity and history

services.py performs transactional writes. New receipts increase shop physical stock. Opening allocations label stock already counted and cannot exceed the unbatched remainder. Quantity edits require a reason and stale quantities are rejected. Purchase receipts reject over-receiving, replay and conflicting batch metadata. Checkout excludes known expired units and allocates known batches by earliest expiry before legacy unbatched stock.

BatchHistory stores before/after snapshots of quantity, supplier, cost, received/expiry dates and removed state. StockMovement remains the physical-stock ledger. Unchanged edits do not duplicate batch history. Earlier events are not invented for pre-existing records. Removed batches retain history, have zero remaining quantity and are hidden from current batches. Removing a stocked batch requires confirmation and a reason; its remaining units are deducted exactly once. Removed batches cannot be edited, adjusted or silently reused by receiving.

CSV exports retain full audit detail; on-screen history is condensed. Reports preserve the chosen medicine/batch/supplier and originating navigation section when dates change. Displayed records are paginated before formatting, and totals are aggregated in the database. CSV text is protected against spreadsheet-formula injection. Inventory is a current snapshot; other reports use their relevant dates.

## Backend structure

models.py defines persisted data and constraints; forms.py validates input; selectors.py implements reusable queries and aggregations; services.py handles audited stock writes; views.py coordinates requests; reusable templates and a shared stylesheet implement the interface. JavaScript handles navigation, form rows, unsaved changes and displaying server-calculated previews. It stores no live catalogue in localStorage.

Migrations preserve existing catalogue metadata and add per-medicine warning periods, removed-batch state and history. Existing medicine names, strengths, selling prices and working data are preserved. Business examples are database records, not runtime arrays embedded in the pages.

## Local access

At the user's request, local development opens the manager without login. This requires DEBUG, MANAGER_LOCAL_PREVIEW and a loopback host/client. Set DJANGO_MANAGER_LOCAL_PREVIEW=false when integrating login. Production still requires an active authorised staff manager and manager.access_manager permission. Customers cannot use that permission to enter the protected workspace. Anonymous local changes do not impersonate staff: actor/created_by remain null. CSRF, validation, transactions and history remain active. Product pages show the role label Manager, without technical preview/sign-in notices.

## Running and verification

    python backend/manage.py migrate
    python backend/manage.py test accounts shop manager --noinput
    python backend/manage.py check
    python backend/manage.py makemigrations --check --dry-run
    python backend/manage.py runserver 127.0.0.1:8017

The working database defaults to backend/db.sqlite3. DJANGO_DATABASE_PATH selects a separate database when provided. The user-approved populated records were imported into the working database on 30 October 2026, preserving existing medicine prices and the original supplier. Database files, private media and secrets are excluded from Git.

Verification on 30 October 2026: all 123 automated tests pass; Django and migration consistency checks pass. Browser checks cover accessible Delete controls and Sign out redirecting to the public Home page. Medicine deletion preserves order and batch history by archiving the catalogue entry. Batch removal preserves history and deducts remaining stock. New medicines use a default image; manager forms do not accept image URLs. Sales reports include customer, item quantities, recorded unit prices, subtotal, other charges and amount paid.

## Deferred team integration

origin/Shreeyash uses separate inventory/orders/prescriptions tables. The user confirmed retaining the shop data source and coordinating integration later. Full clinical state, pickup information and fulfilment timeline require that integration. No IDs or medicine names are assumed to identify equivalent records across those systems.

The shop teammate owns pickup/delivery pricing; no new delivery feature is implemented here. The current checkout's simulated-payment behavior remains. SQLite development checks do not replace production database concurrency/load testing.
