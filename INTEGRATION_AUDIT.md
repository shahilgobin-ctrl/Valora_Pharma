# Integrated application audit — 31 October 2026

Audited branch: merger. Target: origin/main. This audit does not publish to main.

## Merge compatibility

The initial read-only merge simulation found one content conflict, README.md.
The only commit unique to main was its README update. That update was merged
into merger, retaining its structure and correcting the registration description
for merger's existing direct-signup workflow. No application files from other
teams were overwritten by this merge.

Simulations against origin/Home, origin/Pharmacy-Manager, origin/shop,
origin/Shreeyash, origin/Admin and origin/pharmacy-login-register completed
without content conflicts at the audited remote revisions. Future commits can
change this result. A clean Git merge alone does not prove functional correctness.

## One database, shared live data

Django configures one default SQLite database: backend/db.sqlite3 in the
GitHub Desktop checkout. There are no application database routers.

- accounts.User supplies the shared account/session system.
- inventory.Medicine supplies live names, strengths, prices, prescription flags
  and reorder levels.
- inventory.Batch supplies live quantities, supplier information and expiry dates.
- shop.Product supplies categories and the single live medicine image field,
  with an explicit one-to-one medicine link.
- manager.Batch links to the same physical batch and retains manager history.
- orders.Order, OrderItem and Payment serve new customer checkout and pharmacist
  processing; manager reports read these same order/payment records.

The current database contains 12 linked medicines and 15 linked batches.
No product or manager batch lacks its authoritative link. Mirrored quantities
match, SQLite integrity_check returns ok, and foreign_key_check finds no violations.
No required model columns are missing. Local leftover email-verification metadata
is unused; no destructive cleanup was performed.

Three older orders/payments remain in legacy shop tables in this same database.
They are read-only history and are not included in current shared-order reports.
The user approved retaining them. In particular, an older completed order has
no recorded pharmacist/allocation metadata, so converting it automatically would
invent history or risk adjusting stock twice. Current shared orders/payments are
empty in this local demo; no sample sales were fabricated to fill reports.

Separate project folders each retain their own local database. This is different
from application pages using separate databases. Git transfers code/migrations,
not the SQLite records. The working demo is the GitHub Desktop checkout on merger.

## Shared medicine photos

pages migration 0004 promotes the already approved Home photo records into
shop.Product.image. Home now uses Product.image_url, the same resolver as Product,
medicine details, the cart and JSON APIs. No runtime product-name/photo mapping
was added. The earlier Home artwork rows remain as read-only legacy records;
editing a live image now happens through the shared Product image field.

All 12 current medicine images refer to real locally bundled photo files with
credits in frontend/static/shop/products/IMAGE_SOURCES.md and
frontend/static/home/ASSET_SOURCES.md. New manager medicines retain the default
image and managers still have no image-URL input. Prices, quantities, accounts,
orders and the layouts were not changed by the photo migration. The SQLite
file was backed up outside the repository before the migration.

## Verification

- All 330 automated tests across accounts, inventory, orders, prescriptions,
  pharmacist, shop, pages, manager and superadmin passed again after the artwork
  change and README conflict resolution.
- 131 pages/shop/manager tests passed after image consolidation; the image test
  checks Home, catalogue, medicine details and API output, and proves price and
  stock stay unchanged.
- 142 rendered page/report requests across guest, customer, manager, pharmacist
  and administrator roles returned expected responses. Temporary audit accounts
  were created inside a transaction and rolled back.
- All 65 templates compile. No referenced local static files were missing.
- Django system checks and migration/model consistency checks pass.
- Static collection dry run passes; pip check reports no broken requirements.
- All first-party frontend JavaScript files pass node --check syntax validation.

Use explicit app labels when running tests from the repository root; an unlabelled
python backend/manage.py test run there discovers zero tests. For example:

    python backend/manage.py test accounts inventory orders prescriptions pharmacist shop pages manager superadmin --noinput

## Remaining findings and practical limits

1. Existing standalone Shop/Home databases are not automatic upgrade candidates:
   shop migration 0006 deliberately stops when old products lack explicit
   inventory mappings. Back up and provide a reviewed ID mapping before upgrading
   such a database. Fresh migrations and the current integrated database pass.
2. Home and company pages contain fixed contact/branch and registration text;
   these are not all loaded from PharmacyProfile. Medicine prices, stock and
   orders are database-driven, but claiming the whole site has no hardcoded
   business information would be inaccurate. Contact configuration needs a
   separate agreed content model to prevent inconsistent company details.
3. Checkout payments are explicitly simulated; no real payment provider is
   connected. Development email uses the terminal unless SMTP is configured.
4. Default local development uses SQLite, a development server and a per-process
   cache. Concurrent production behavior, real email delivery and real payments
   are outside this local test result. The terms text is still labelled draft.
5. Automated request checks do not replace reviewing every screen visually on
   every browser/device. The shared photo and navigation changes were checked
   in the local browser without changing public page layouts.

The database and private media remain local and are not committed or deleted.


## Local folder alignment

The original and GitHub Desktop checkouts now use the merger branch. The original
checkout selects the GitHub Desktop backend directory using its ignored local
backend/.data-directory pointer. Consequently their normal development settings
resolve the same database, private uploads and development session key. The
original standalone database is preserved, and both databases were backed up
before this configuration. The shared-directory setting contains no PC paths in
Git and has four configuration regression tests. Defaults remain unchanged for
other team members who do not configure a shared directory.

Code edits still require committing/pushing from one checkout and pulling in the
other. Separate checkout folders do not mirror uncommitted file edits.
