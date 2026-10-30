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
review. It never matches medicine names heuristically. The previously
separate manager tables have no records in the current showcase database.

Manager access requires an active staff account with the `Pharmacy Managers`
group permission. Pharmacists keep their own dashboard redirect. Anonymous
local preview access is disabled. Administrators retain their own login home.

The shared test suite covers receipt visibility in shop and pharmacist pages,
pharmacist completion, expiry handling, payments, access rules and redirects.
Browser layout checks remain necessary after migrations are applied.
