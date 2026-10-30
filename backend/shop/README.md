# Integrated public storefront

Home and Shop display inventory.Medicine records through linked shop.Product presentation metadata. Medicine names, strengths, descriptions, decimal prices, selling units, active states and prescription flags come from inventory. Available quantities use unexpired batches less pending online order quantities. Shop categories and images are presentation metadata, not dispensing data.

New customer checkout writes orders.Order, orders.OrderItem and one orders.Payment marked as simulated online payment. It does not deduct batch stock. Prescription uploads create prescriptions.Prescription records for the pharmacist review queue. Pharmacist fulfilment reuses that payment, checks approved prescriptions and batch allocations, and deducts stock once at completion. Cancellation retains the simulated payment with a refund timestamp. No real payment provider is used.

The historical shop.Order, shop.OrderItem and shop.Payment tables remain for compatibility and history; checkout does not write to them. Their admin screens are read-only. Legacy Product commercial columns are retained but do not supply public prices, stock or prescription flags. Unlinked legacy products are not publicly sold.

The compatibility seed_shop command only links existing inventory records; it does not import the sample JSON, create medicine records or change stock. --update-existing is rejected. No seeding command is needed to upgrade the existing showcase database: shop.0006 creates storefront metadata for its existing medicines. If pre-existing shop products are present, that migration deliberately stops for explicit mapping rather than guessing strengths or pack sizes.
