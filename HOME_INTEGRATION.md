# Home integration review - 30 October 2026

The starting merger branch was d23f677 with an existing unfinished merge of Home 45d10ed. The integration preserves the pharmacist apps, private upload root, shared authentication, verification/recovery flows, customer safe-next links and Pharmacist-group dashboard routing. Customers default to the public Home page; protected role landing pages retain their access restrictions.

Public Home, Shop, cart and About navigation uses named routes. About retains its isolated design and uses POST/CSRF logout for authenticated users. Auth, Home, Shop, About and pharmacist styles remain isolated. Pharmacy profile context data is lazy so public informational templates do not query it unnecessarily.

Inventory is authoritative for public medicines and stock. Storefront records supply only presentation metadata. Customer checkout places orders in the existing pharmacist queue, records a simulated payment once, and defers batch deductions to pharmacist completion. Pending online orders reduce public availability. Uploaded prescriptions enter the existing private review workflow. Simulated cancellation records a refund timestamp; it does not delete payment history.

## Validation

Run the full suite from backend with `..\.venv\Scripts\python.exe manage.py test --noinput`. Installed local apps: accounts, pharmacist, prescriptions, inventory, orders, shop and pages. The integrated suite has 217 tests, including 8 new cross-app fulfilment tests. Django checks, migration consistency and JavaScript syntax checks are also run.

A disposable SQLite copy of the showcase database successfully upgraded. Comparisons preserved every existing row and column, allowing only additional Django migration/content-type/permission metadata. All 25 existing medicines acquired storefront presentation links in the copy. The real database and 24 private uploaded files remain byte-for-byte unchanged.

## Pending migrations on the real database

Do not apply these during this integration. The current plan is orders.0006 (delivery metadata and simulated payment/refund flags), shop.0001 through shop.0006 (retained legacy schema, presentation/cart settings and explicit inventory links), and pages.0001 (homepage artwork overrides). Existing migration files are retained. No database reset or sample catalogue import is required.

## Remaining work

The user refreshed origin through GitHub Desktop. Local remote references confirm Home 45d10ed, shop 0286458 and About-page 20650be. No further fetch was performed. Home is ready for its authorised merge commit, followed by shop and About-page in order. Browser checks remain: responsive navigation, customer verification and return-to-cart, shop filters and decimal selling-unit labels, prescription upload/review, simulated checkout, and pharmacist allocation/completion/receipt. No real SMTP or payment verification was performed.


## Shop integration

Merged source: origin/shop at 0286458. Preserved the updated shop palette, photographs and delivery/pickup controls. All navigation uses named public routes and logout remains POST-only with CSRF. Pickup has no fee in the server-rendered cart and checkout; delivery uses ShopSettings rather than the branch's hard-coded amount. Currency keeps inventory decimal precision. The incoming simulated-payment regression is retained against orders.Payment, with additional pickup, invalid-method and photograph-preservation tests.

The parallel shop migration histories are retained and joined by shop.0007_merge_shop_histories. Incoming shop.0004_product_photographs and shop.0005_order_delivery_method remain intact; the legacy shop Order delivery field is retained for history, while new orders use orders.Order. Local product photographs are a fallback for empty presentation artwork; custom artwork remains unchanged.
