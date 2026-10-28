# Catalogue data and backend structure

The public homepage and shop use the same Product and Category database tables. Prices, names, strengths, descriptions, stock, prescription flags and image paths are editable in Django admin under Shop > Products. No product-name lookup table or frontend price list is used.

Product images are the original files from the teammate shop branch. Product.image may be an existing /static/ URL, an HTTP(S) URL, or a static-relative path such as shop/products/paracetamol.svg. The shared image resolver supplies one generic fallback when the field is empty. Condition cards choose an active product image from their database category; no hardcoded medicine-to-condition mapping is used.

- models.py: stored catalogue, carts, orders and shop settings.
- selectors.py: shared catalogue and category-image queries and cart quantity.
- images.py: common image URL resolution for HTML and JSON.
- pricing.py: common totals for cart API, cart page and checkout.
- views.py: request handling; templates render database values.
- serializers.py: database records as JSON.
- admin.py: authorised editing of the catalogue and delivery charge.
- migrations/: schema evolution and one-time historical data transfers.

Delivery is editable under Shop > Shop settings. Migration 0004 preserves the previous Rs 100 charge as a database value. There is no fixed runtime delivery charge. Empty carts have no delivery charge. Checkout recalculates from stored product prices; submitted price/total values are ignored. OrderItem.unit_price snapshots the price at order time, so later catalogue changes do not rewrite historical orders.

The optional seed_shop command reads data/demo_catalogue.json. Those are sample records, not verified live stock. It is never called by views, app startup or migrations. By default it adds missing sample products and preserves existing records, including edited prices/images. --update-existing explicitly replaces matching products with the sample data. Use admin for normal catalogue maintenance.

Run checks with:

    python backend/manage.py check
    python backend/manage.py makemigrations --check --dry-run
    python backend/manage.py test accounts pages shop

The separate pharmacist inventory/orders models have not been consolidated into this shop app. Payment integration is still the existing local placeholder; this catalogue audit does not activate a payment gateway.


## Representative visual refresh

The four homepage sample products now use representative Pexels photographs; remaining catalogue images retain their existing artwork. Source and licence information is in frontend/static/home/ASSET_SOURCES.md. All files are served locally.

Edit Category.image and Category.display_order in admin to select and order the small condition illustrations. If Category.image is empty, the product-derived fallback still works. Edit Product.image and Product.homepage_order to select photographs and prioritise homepage cards. Shop settings includes the editable hero_image field. These are database values; the migration only sets initial values for the existing sample catalogue while preserving custom product images.


## Homepage image isolation correction

Representative photographs now live in pages.HomepageProductImage, not Product.image. The homepage selector attaches the override only for home.html. Shop catalogue/detail/cart pages and the product API continue to use the original Product.image. The prior visual update's shop image values were restored. Prices and stock were not changed. To edit homepage photographs, use Pages > Homepage product images in admin.
