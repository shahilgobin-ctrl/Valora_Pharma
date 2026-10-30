# Public page integration - 30 October 2026

## Sources and local merges

The user refreshed origin through GitHub Desktop; no fetch was performed during the final integration pass. Local remote references were Home 45d10ed, shop 0286458 and About-page 20650be. They were integrated on merger in that order. Home was committed as e8b2073 and shop as 6be73fd; About-page is the final merge.

## Integrated behaviour

The public Home, Shop, cart and About pages use working named navigation routes. Customers default to Home and retain safe return-to-Shop/cart destinations through registration and verification. Shared authentication, email verification, password recovery and role restrictions are preserved. Active staff in the Pharmacist group continue to reach pharmacist:dashboard. Authenticated public headers use POST/CSRF logout.

Inventory Medicine records are authoritative for medicine names, strengths, decimal prices, selling units, descriptions, prescription flags and active states. Public availability uses unexpired batches less pending online orders. Storefront records supply presentation metadata. Customer checkout writes the existing orders.Order queue, records one simulated online orders.Payment, and defers physical stock deductions to pharmacist completion. Uploaded prescriptions enter the existing private review workflow. Completion reuses the online payment and deducts batch stock once; cancellation retains the simulated payment with a refund timestamp. The legacy shop order/payment tables remain read-only history and are not used by new checkout.

The shop branch's updated palette, photographs and delivery/pickup controls are retained. Delivery uses ShopSettings; pickup has no fee in the rendered cart or checkout. Decimal currency and explicit selling-unit labels are retained. Empty artwork can use the incoming local photographs; custom artwork is preserved. The incoming successful-demo-payment regression is retained against the shared payment model.

The About design and embedded resources remain isolated from authentication, shop and pharmacist CSS. Its standalone preview and export tool are retained and the preview was regenerated. Public links and authenticated logout work in the Django version; unavailable preview actions remain disabled. The informational view remains free of application database queries for anonymous visitors; the pharmacy profile context processor is lazy.

## Validation

The full suite was discovered from backend using `..\.venv\Scripts\python.exe manage.py test --noinput`. Installed local apps: accounts, pharmacist, prescriptions, inventory, orders, shop and pages. Home passed 217 tests, shop passed 221 tests, and the final combined result passed 226 tests. Django check reported no issues; makemigrations --check --dry-run found no changes. Home and Shop JavaScript passed node --check.

A disposable copy of the configured showcase SQLite database successfully upgraded through the entire final migration graph. Every original row and column was compared and preserved; only new Django migration/content-type/permission metadata was allowed. SQLite integrity was OK. All 25 existing medicines acquired storefront presentation links in the copy. The existing pharmacist was checked on that copy: active staff role, Pharmacist membership, dashboard HTTP 200 and shared-login dashboard redirect all passed.

The real database and all 24 private uploads remain byte-for-byte unchanged. No migrations or seed commands were run against the real database. No migration history was deleted.

## Pending migrations on the real database

- orders.0006_order_delivery_fee_order_delivery_method_and_more
- shop.0001_initial, 0002_payment, 0003_shop_images_and_prescriptions
- shop.0004_shopsettings and 0005_homepage_visuals
- pages.0001_homepage_product_images
- shop.0006_product_medicine
- shop.0004_product_photographs and 0005_order_delivery_method
- shop.0007_merge_shop_histories

Both parallel shop migration histories are retained and joined by 0007. No reset or sample import is required. The inventory-link migration deliberately stops if it encounters pre-existing shop products needing an explicit medicine/strength/pack mapping. It succeeds on the verified showcase copy, which has no legacy shop products. Review this plan and back up the configured database and uploads before authorising a real upgrade. Convenience startup scripts apply migrations automatically and should wait until that review is complete.

## Remaining browser checks

Check desktop/mobile navigation and page layouts, login/verification/return-to-cart, shop filters and selling-unit labels, delivery/pickup totals, prescription upload/review, simulated checkout and pharmacist allocation/completion/receipt. The standalone About preview should also be opened locally. Browser interaction, real SMTP delivery and real payments were not tested in this combined pass. No push or deployment was performed.
