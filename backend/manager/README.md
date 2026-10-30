# Pharmacy Manager integration

The manager workspace uses the same physical inventory and orders as the
pharmacist and public shop. `inventory.Medicine` owns names, prices,
prescription requirements and reorder levels. `inventory.Batch` owns physical
quantities, expiry dates, supplier names and purchase costs. `shop.Product`
supplies storefront artwork and categories through its explicit `medicine`
link. Its legacy price, stock and prescription columns remain for old records
and are not changed by manager workflows.

Manager suppliers, purchase orders, receiving history and audit records remain
in the manager app. A manager `Batch` row is linked one-to-one to its physical
inventory batch for the existing reporting interface and history. Receipts,
edits, adjustments and removals update the physical batch in one transaction.
Pharmacist completion deducts that same physical batch and updates the linked
manager reporting quantity in the same transaction. Shop availability reads
physical unexpired batches and pending order reservations directly.

Migration `0005_link_existing_inventory` creates reporting links only from
the existing `shop.Product.medicine_id` and exact `inventory.Batch` IDs.
If old, unlinked manager batches are present, migration stops for explicit
review. It never matches medicine names heuristically. Previously separate manager records require an explicit, reviewed link to physical inventory; they must not be imported without that mapping.

Manager access requires an active staff account with the `Pharmacy Managers`
group permission. Pharmacists keep their own dashboard redirect. Anonymous
local preview access is disabled. Administrators retain their own login home.

The shared test suite covers receipt visibility in shop and pharmacist pages,
pharmacist completion, expiry handling, payments, access rules and redirects.
Browser layout checks remain necessary after migrations are applied.


## Home and manager parity

The merger workspace retains the accessible medicine/batch Delete controls,
confirmation and history preservation, image-free medicine forms with a default
image for new medicines, and POST Sign out returning to the original public Home.
Sales reports use the integrated order/payment records with customer, item,
quantity and saved-price detail. Do not replace these reads with the older
Pharmacy-Manager branch's separate order tables.

Home categories and medicine cards are database-driven. Git pulls transfer code,
not local SQLite records. An empty checkout must receive a reviewed data import
and explicit inventory links; restarting the server does not populate categories.
On 30 October 2026 the local merger demo received the approved 8 categories,
12 linked medicines and 15 linked batches. The destination was backed up first;
no database or private-media files were removed or committed.

Regression tests in test_shared_inventory.py cover the manager controls, default
image, sign-out destination and Home category filtering alongside the existing
physical-inventory integration checks. Shared shop, authentication, pharmacist
and administrator source files are unchanged by this parity update.


On 31 October 2026, the separate manager Home link was removed: Sign out clears
the session and redirects to the named public Home route. Home has a single Shop
navigation link; other teams' headers are unchanged. Missing Home artwork is
restored by pages migration 0003 using separate HomepageProductImage records,
without replacing shop images or duplicating catalogue products. Existing custom
Home artwork is preserved. Home shows its configured featured selection; the
full catalogue contains newly added manager medicines. Manager edits update the
linked authoritative medicine, so Home reads the current saved name and price.


The later 31 October audit unified Home and Product artwork: pages migration 0004
promotes approved Home photos into shop.Product.image, now the shared live field.
The previous separate Home image rows are retained read-only for history. See
INTEGRATION_AUDIT.md for database mapping and the full validation results.
