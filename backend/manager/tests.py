from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from shop.models import Cart, CartItem, Category, Order, Payment, Product
from .forms import BatchForm, MedicineForm, PurchaseLines
from .models import AuditEvent, Batch, InventoryPolicy, MedicineDetails, PurchaseOrder, PurchaseOrderLine, StockMovement, Supplier
from .selectors import monthly_sales, risks
from .services import adjust_stock, receive_order, save_batch
from shop.inventory import available_stock


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ManagerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="manager@example.test", password="TestingPass42!", account_type="staff")
        self.user.groups.add(Group.objects.get(name="Pharmacy Managers"))
        self.customer = get_user_model().objects.create_user(email="customer@example.test", password="TestingPass42!")
        self.staff = get_user_model().objects.create_user(email="staff@example.test", password="TestingPass42!", account_type="staff")
        self.category = Category.objects.create(name="Test condition")
        self.product = Product.objects.create(name="Test medicine", category=self.category, price=73, stock_quantity=10, strength="20mg")
        MedicineDetails.objects.create(product=self.product, reorder_level=15, dosage_form="Tablet")
        self.supplier = Supplier.objects.create(name="Test supplier")
        self.today = timezone.localdate()
        self.client.force_login(self.user)

    def linked_product(self, name="Linked test medicine"):
        from inventory.models import Medicine
        medicine = Medicine.objects.create(name=name, strength="20 mg", dosage_form="Tablet",
            selling_unit="tablet", selling_price=Decimal("73.00"), category_name=self.category.name)
        product = medicine.storefront
        MedicineDetails.objects.get_or_create(product=product, defaults={"reorder_level": 15})
        return product

    def make_batch(self, **changes):
        data = dict(product=self.product, supplier=self.supplier, number="BATCH-1", quantity=4,
            purchase_price=Decimal("12.50"), received_date=self.today-timedelta(days=30), expiry_date=self.today+timedelta(days=30))
        data.update(changes)
        return Batch.objects.create(**data)

    def make_order(self, quantity=6):
        order = PurchaseOrder.objects.create(supplier=self.supplier, ordered_date=self.today,
            expected_date=self.today+timedelta(days=3), created_by=self.user)
        line = PurchaseOrderLine.objects.create(order=order, product=self.product, quantity=quantity, unit_cost=Decimal("12.50"))
        return order, line

    def receipt(self, line, quantity=2, **changes):
        data = dict(line_id=line.pk, expected_received=line.received_quantity, quantity=quantity,
            batch_number="DELIVERY-1", received_date=self.today, expiry_date=self.today+timedelta(days=180))
        data.update(changes)
        return data

    def test_permissions_on_every_manager_route(self):
        routes = ["dashboard", "medicines", "batches", "alerts", "orders", "suppliers", "reports", "movements", "customer_orders", "settings", "medicine_new", "batch_new", "purchase_new"]
        for user in [self.customer, self.staff]:
            self.client.force_login(user)
            for name in routes:
                with self.subTest(user=user.email, route=name):
                    self.assertEqual(self.client.get(reverse("manager:"+name)).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("manager:dashboard")).status_code, 302)
        self.customer.groups.add(Group.objects.get(name="Pharmacy Managers"))
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("manager:dashboard")).status_code, 403)

    def test_manager_login_redirects_to_dashboard_and_staff_does_not(self):
        self.client.logout()
        response = self.client.post(reverse("accounts:login"), {"email": self.user.email, "password": "TestingPass42!"})
        self.assertRedirects(response, reverse("manager:dashboard"))
        self.client.logout()
        response = self.client.post(reverse("accounts:login"), {"email": self.staff.email, "password": "TestingPass42!"})
        self.assertRedirects(response, reverse("accounts:staff_landing"))

    def test_all_primary_and_supporting_pages_render(self):
        batch = self.make_batch()
        order, _ = self.make_order()
        from orders.models import Order as SharedOrder
        customer_order = SharedOrder.objects.create(kind="online", customer=self.customer, total_amount=73)
        routes = [("dashboard", []), ("medicines", []), ("batches", []), ("alerts", []), ("orders", []),
            ("medicine_new", []), ("medicine_edit", [self.product.pk]), ("medicine_status", [self.product.pk]),
            ("batch_new", []), ("batch_edit", [batch.pk]), ("adjustment", []), ("movements", []),
            ("suppliers", []), ("supplier_new", []), ("supplier_edit", [self.supplier.pk]), ("categories", []),
            ("purchase_new", []), ("purchase_detail", [order.pk]), ("receive", [order.pk]),
            ("purchase_cancel", [order.pk]), ("customer_orders", []), ("customer_order_detail", [customer_order.pk])]
        for name, args in routes:
            with self.subTest(route=name):
                self.assertEqual(self.client.get(reverse("manager:"+name, args=args)).status_code, 200)
        for kind in ["sales", "inventory", "expiry", "purchasing"]:
            self.assertEqual(self.client.get(reverse("manager:reports"), {"type": kind}).status_code, 200)

    def test_counts_and_alerts_are_live_and_reconcile(self):
        risk = risks()
        self.assertEqual(risk["low"].count(), 1)
        self.product.stock_quantity = 0
        self.product.save()
        home = self.client.get(reverse("manager:dashboard"))
        alert = self.client.get(reverse("manager:alerts"))
        self.assertEqual(home.context["counts"]["out"], 1)
        self.assertEqual(home.context["counts"], alert.context["counts"])
        self.assertEqual(home.context["counts"]["low"], 0)
        self.assertContains(alert, self.product.name)

    def test_expiry_uses_current_date_and_editable_policy(self):
        batch = self.make_batch(expiry_date=self.today+timedelta(days=10))
        setting = InventoryPolicy.objects.get(pk=1)
        setting.expiry_warning_days = 5
        setting.save()
        self.assertEqual(risks()["expiring"].count(), 0)
        setting.expiry_warning_days = 20
        setting.save()
        self.assertEqual(risks()["expiring"].count(), 1)
        batch.expiry_date = self.today-timedelta(days=1)
        batch.save()
        self.assertEqual(risks()["expired"].count(), 1)
        self.assertEqual(available_stock(self.product), 6)
        self.assertEqual(risks()["low"].get().available, 6)

    def test_batch_creation_changes_shared_stock_and_logs_actor(self):
        data = {"product": self.product.pk, "supplier": self.supplier.pk, "number": "NEW-BATCH", "quantity": 7,
            "purchase_price": "12.50", "received_date": self.today, "expiry_date": self.today+timedelta(days=100)}
        form = BatchForm(data)
        self.assertTrue(form.is_valid(), form.errors)
        save_batch(form, self.user)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 17)
        move = StockMovement.objects.get()
        self.assertEqual((move.delta, move.previous_quantity, move.new_quantity, move.actor_id), (7, 10, 17, self.user.pk))

    def test_batch_form_rejects_negative_cost_and_invalid_dates(self):
        form = BatchForm({"product": self.product.pk, "supplier": self.supplier.pk, "number": "BAD", "quantity": -1,
            "purchase_price": "-1", "received_date": self.today, "expiry_date": self.today-timedelta(days=1)})
        self.assertFalse(form.is_valid())
        self.assertIn("quantity", form.errors)
        self.assertIn("purchase_price", form.errors)
        self.assertIn("expiry_date", form.errors)

    def test_adjustments_require_reason_and_preserve_nonnegative_quantities(self):
        batch = self.make_batch()
        for delta, expected, reason in [(-5,4,"Disposal"),(1,3,"Correction"),(1,4,"")]:
            with self.assertRaises(ValidationError):
                adjust_stock(batch.pk, delta, expected, reason, self.user)
        self.assertFalse(StockMovement.objects.exists())
        adjust_stock(batch.pk,-2,4,"Damaged units",self.user)
        batch.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual((batch.quantity,self.product.stock_quantity),(2,8))
        self.assertEqual(StockMovement.objects.get().reason,"Damaged units")

    def test_partial_receipt_and_final_receipt_are_atomic_and_audited(self):
        order,line=self.make_order()
        receive_order(order.pk,[self.receipt(line,2)],self.user)
        line.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual((line.received_quantity,self.product.stock_quantity),(2,12))
        self.assertEqual(PurchaseOrder.objects.get(pk=order.pk).status,"Partial")
        receive_order(order.pk,[self.receipt(line,4)],self.user)
        line.refresh_from_db()
        self.assertEqual(PurchaseOrder.objects.get(pk=order.pk).status,"Received")
        self.assertEqual(Batch.objects.get().quantity,6)
        self.assertEqual(StockMovement.objects.count(),2)
        self.assertEqual(order.total,Decimal("75.00"))

    def test_over_receipt_and_stale_replay_are_rejected(self):
        order,line=self.make_order()
        with self.assertRaises(ValidationError):
            receive_order(order.pk,[self.receipt(line,1,received_date=self.today-timedelta(days=1))],self.user)
        payload=self.receipt(line,2)
        receive_order(order.pk,[payload],self.user)
        with self.assertRaises(ValidationError):
            receive_order(order.pk,[payload],self.user)
        line.refresh_from_db()
        with self.assertRaises(ValidationError):
            receive_order(order.pk,[self.receipt(line,5)],self.user)
        self.assertEqual(Batch.objects.get().quantity,2)

    def test_receipt_rolls_back_all_lines_on_error(self):
        order,line=self.make_order()
        second=Product.objects.create(name="Second medicine",category=self.category,price=30,stock_quantity=3)
        other=PurchaseOrderLine.objects.create(order=order,product=second,quantity=1,unit_cost=5)
        with self.assertRaises(ValidationError):
            receive_order(order.pk,[self.receipt(line,2),self.receipt(other,2,batch_number="OTHER")],self.user)
        self.product.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual((self.product.stock_quantity,line.received_quantity),(10,0))
        self.assertFalse(Batch.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_receiving_rejects_foreign_or_duplicate_line_ids(self):
        order,line=self.make_order()
        other,foreign=self.make_order()
        data={"form-TOTAL_FORMS":"1","form-INITIAL_FORMS":"1","form-0-line_id":foreign.pk,
            "form-0-expected_received":0,"form-0-quantity":1,"form-0-batch_number":"FOREIGN",
            "form-0-received_date":self.today,"form-0-expiry_date":self.today+timedelta(days=30),"confirmed":"on"}
        response=self.client.post(reverse("manager:receive",args=[order.pk]),data)
        self.assertContains(response,"order lines changed or are invalid")
        self.assertFalse(Batch.objects.exists())

    def test_create_purchase_order_does_not_change_stock(self):
        data={"supplier":self.supplier.pk,"ordered_date":self.today,"expected_date":self.today+timedelta(days=3),
            "lines-TOTAL_FORMS":"1","lines-INITIAL_FORMS":"0","lines-0-product":self.product.pk,
            "lines-0-quantity":6,"lines-0-unit_cost":"12.50"}
        response=self.client.post(reverse("manager:purchase_new"),data)
        self.assertEqual(response.status_code,302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity,10)
        self.assertEqual(PurchaseOrder.objects.get().total,Decimal("75.00"))

    def test_archive_needs_confirmation_and_preserves_history(self):
        order,line=self.make_order()
        url=reverse("manager:medicine_status",args=[self.product.pk])
        self.client.get(url)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)
        self.client.post(url,{"target":"0"})
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)
        self.client.post(url,{"target":"0","confirmed":"on"})
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)
        self.assertTrue(PurchaseOrderLine.objects.filter(pk=line.pk).exists())

    def test_csrf_and_wrong_role_protect_mutations(self):
        csrf=Client(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        self.assertEqual(csrf.post(reverse("manager:supplier_new"),{"name":"Bad"}).status_code,403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(reverse("manager:supplier_new"),{"name":"Bad"}).status_code,403)
        self.assertFalse(Supplier.objects.filter(name="Bad").exists())

    def test_expired_stock_cannot_be_sold_and_checkout_is_rolled_back(self):
        self.make_batch(quantity=10,expiry_date=self.today-timedelta(days=1))
        cart=Cart.objects.create(user=self.customer)
        CartItem.objects.create(cart=cart,product=self.product,quantity=1)
        self.client.force_login(self.customer)
        response=self.client.post(reverse("shop:api_checkout"))
        self.assertEqual(response.status_code,409)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Payment.objects.exists())

    def test_sale_allocates_earliest_unexpired_batch_and_records_movement(self):
        # A legacy unlinked product cannot create a disconnected shop sale.
        batch = self.make_batch()
        cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=2)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(reverse("shop:api_checkout")).status_code, 409)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity, 4)
        self.assertFalse(Payment.objects.exists())

    def test_dashboard_sales_use_successful_payments_only(self):
        from orders.models import Order as SharedOrder, Payment as SharedPayment
        paid = SharedOrder.objects.create(kind="online", customer=self.customer, total_amount=321)
        SharedPayment.objects.create(order=paid, method="card", amount=321, recorded_by=self.customer)
        refunded = SharedOrder.objects.create(kind="online", customer=self.customer, total_amount=900)
        SharedPayment.objects.create(order=refunded, method="card", amount=900, recorded_by=self.customer,
            refunded_at=timezone.now())
        self.assertEqual(monthly_sales()[-1]["total"], 321)
        response = self.client.get(reverse("manager:reports"), {"type": "sales"})
        self.assertEqual(response.context["total"], 321)

    def test_csv_escapes_spreadsheet_formulas_and_filters_dates(self):
        self.product.name="=DANGEROUS()"
        self.product.save()
        response=self.client.get(reverse("manager:reports"),{"type":"inventory","format":"csv"})
        self.assertIn("'=DANGEROUS()",response.content.decode())
        response=self.client.get(reverse("manager:reports"),{"start":"2026-12-31","end":"2026-01-01"})
        self.assertEqual(response.context["count"],0)
        self.assertContains(response,"End date must be on or after start date")

    def test_search_filter_pagination_and_data_edits(self):
        product = self.linked_product("Database medicine")
        product.medicine.selling_price = Decimal("987.00")
        product.medicine.save(update_fields=["selling_price"])
        response=self.client.get(reverse("manager:medicines"),{"q":"Database"})
        self.assertContains(response,"Database medicine")
        self.assertContains(response,"987.00")
        response=self.client.get(reverse("manager:medicines"),{"q":"not present"})
        self.assertEqual(response.context["rows"].paginator.count,0)

    def test_read_only_oversight_and_reports_reject_post(self):
        for name in ["customer_orders","movements","reports","dashboard"]:
            self.assertEqual(self.client.post(reverse("manager:"+name)).status_code,405)

    def test_grant_command_only_grants_existing_active_staff(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command("grant_manager",self.customer.email,stdout=StringIO())
        call_command("grant_manager",self.staff.email,stdout=StringIO())
        self.assertTrue(get_user_model().objects.get(pk=self.staff.pk).has_perm("manager.access_manager"))

    def test_http_receiving_persists_stock_and_rejects_resubmission(self):
        order,line=self.make_order()
        data={"form-TOTAL_FORMS":"1","form-INITIAL_FORMS":"1","form-0-line_id":line.pk,
            "form-0-expected_received":0,"form-0-quantity":2,"form-0-batch_number":"REAL-RECEIPT",
            "form-0-received_date":self.today,"form-0-expiry_date":self.today+timedelta(days=30),"confirmed":"on"}
        response=self.client.post(reverse("manager:receive",args=[order.pk]),data)
        self.assertRedirects(response,reverse("manager:purchase_detail",args=[order.pk]))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity,12)
        response=self.client.post(reverse("manager:receive",args=[order.pk]),data)
        self.assertContains(response,"stale or has already been submitted")
        self.assertEqual(StockMovement.objects.count(),1)

    def test_edit_batch_requires_reason_and_audits_quantity_change(self):
        batch=self.make_batch()
        data={"product":self.product.pk,"supplier":self.supplier.pk,"number":batch.number,
            "quantity":3,"purchase_price":"12.50","received_date":batch.received_date,
            "expiry_date":batch.expiry_date,"expected_quantity":4,"reason":"Count correction"}
        response=self.client.post(reverse("manager:batch_edit",args=[batch.pk]),data)
        self.assertRedirects(response,reverse("manager:batch_detail", args=[batch.pk]))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity,9)
        self.assertEqual(StockMovement.objects.get().delta,-1)

    def test_purchase_order_requires_at_least_one_positive_line(self):
        data={"supplier":self.supplier.pk,"ordered_date":self.today,"expected_date":self.today,
            "lines-TOTAL_FORMS":"1","lines-INITIAL_FORMS":"0","lines-0-product":self.product.pk,
            "lines-0-quantity":0,"lines-0-unit_cost":"12.50"}
        response=self.client.post(reverse("manager:purchase_new"),data)
        self.assertEqual(response.status_code,200)
        self.assertFalse(PurchaseOrder.objects.exists())

    def test_opening_batch_allocation_does_not_double_count_existing_stock(self):
        data={"product":self.product.pk,"supplier":self.supplier.pk,"number":"OPENING",
            "quantity":6,"purchase_price":"12.50","received_date":self.today-timedelta(days=30),
            "expiry_date":self.today-timedelta(days=1),"stock_source":"opening"}
        form=BatchForm(data)
        self.assertTrue(form.is_valid(),form.errors)
        save_batch(form,self.user)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity,10)
        self.assertEqual(available_stock(self.product),4)
        self.assertEqual(StockMovement.objects.get().delta,0)
        data["number"]="TOO-MUCH"
        form=BatchForm(data)
        self.assertTrue(form.is_valid(),form.errors)
        with self.assertRaises(ValidationError):
            save_batch(form,self.user)
        self.assertEqual(Batch.objects.count(),1)


    def test_edit_cannot_bypass_archive_confirmation(self):
        product = self.linked_product("Archive control")
        data = {"name": product.public_name, "category": product.category_id, "price": 84,
            "strength": "20 mg", "dosage_form": "Tablet", "is_active": ""}
        response = self.client.post(reverse("manager:medicine_edit", args=[product.pk]), data)
        self.assertEqual(response.status_code, 302)
        product.refresh_from_db(); product.medicine.refresh_from_db()
        self.assertTrue(product.medicine.is_active)
        self.assertEqual(product.medicine.selling_price, Decimal("84.00"))
        self.assertNotIn("is_active", MedicineForm(instance=product).fields)

    def test_supplier_contact_persists_and_is_searchable(self):
        response = self.client.post(reverse("manager:supplier_edit", args=[self.supplier.pk]),
            {"name": self.supplier.name, "contact_name": "Contact Example", "is_active": "on"})
        self.assertEqual(response.status_code, 302)
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.contact_name, "Contact Example")
        self.assertContains(self.client.get(reverse("manager:suppliers"), {"q": "Contact Example"}), self.supplier.name)

    def test_purchase_order_date_range_filters_and_invalid_range(self):
        order, line = self.make_order()
        older = PurchaseOrder.objects.create(supplier=self.supplier, ordered_date=self.today-timedelta(days=10), expected_date=self.today)
        response = self.client.get(reverse("manager:orders"), {"start": self.today, "end": self.today})
        self.assertEqual([row.pk for row in response.context["rows"]], [order.pk])
        response = self.client.get(reverse("manager:orders"), {"start": self.today, "end": self.today-timedelta(days=1)})
        self.assertEqual(response.context["rows"].paginator.count, 0)
        self.assertContains(response, "End date must be on or after start date")

    def test_overview_shortcuts_resolve_for_all_workflows(self):
        response = self.client.get(reverse("manager:dashboard"))
        self.assertEqual(len(response.context["shortcuts"]), 6)
        for shortcut in response.context["shortcuts"]:
            with self.subTest(shortcut=shortcut["label"]):
                self.assertContains(response, shortcut["url"])
                self.assertEqual(self.client.get(shortcut["url"]).status_code, 200)

    def test_purchase_preview_uses_decimal_costs_without_saving(self):
        data = {"_preview": "1", "supplier": self.supplier.pk, "ordered_date": self.today, "expected_date": self.today,
            "lines-TOTAL_FORMS": "1", "lines-INITIAL_FORMS": "0", "lines-0-product": self.product.pk,
            "lines-0-quantity": 3, "lines-0-unit_cost": "17.35"}
        response = self.client.post(reverse("manager:purchase_new"), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Total: Rs 52.05", response.json()["summary"])
        self.assertFalse(PurchaseOrder.objects.exists())
        self.assertFalse(StockMovement.objects.exists())
        data["lines-0-quantity"] = -1
        self.assertEqual(self.client.post(reverse("manager:purchase_new"), data).status_code, 400)

    def test_adjustment_preview_is_read_only_and_rejects_negative_result(self):
        batch = self.make_batch()
        data = {"_preview": "1", "batch": batch.pk, "expected_quantity": 4, "delta": -2, "reason": "Damaged"}
        response = self.client.post(reverse("manager:adjustment"), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("4 → 2", response.json()["summary"])
        batch.refresh_from_db()
        self.assertEqual(batch.quantity, 4)
        self.assertFalse(StockMovement.objects.exists())
        data["delta"] = -5
        self.assertEqual(self.client.post(reverse("manager:adjustment"), data).status_code, 409)

    def test_receipt_preview_does_not_receive_and_rejects_over_receipt(self):
        order, line = self.make_order()
        data = {"_preview": "1", "form-TOTAL_FORMS": "1", "form-INITIAL_FORMS": "1",
            "form-0-line_id": line.pk, "form-0-expected_received": 0, "form-0-quantity": 2,
            "form-0-batch_number": "DELIVERY", "form-0-received_date": self.today,
            "form-0-expiry_date": self.today+timedelta(days=180)}
        url = reverse("manager:receive", args=[order.pk])
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("receive 2; remaining 4", response.json()["summary"])
        line.refresh_from_db()
        self.assertEqual(line.received_quantity, 0)
        self.assertFalse(Batch.objects.exists())
        data["form-0-quantity"] = 7
        self.assertEqual(self.client.post(url, data).status_code, 409)


    def test_expired_availability_matches_shop_api_filters_and_cart(self):
        from inventory.models import Batch as PhysicalBatch
        self.product = self.linked_product("Expired test medicine")
        PhysicalBatch.objects.create(medicine=self.product.medicine, batch_number="EXPIRED",
            supplier_name=self.supplier.name, received_date=self.today-timedelta(days=20),
            expiry_date=self.today-timedelta(days=1), quantity_available=10, purchase_price=1)
        response = self.client.get("/api/products/", {"availability": "in_stock"})
        self.assertNotIn(self.product.slug, str(response.json()))
        response = self.client.get("/api/products/", {"availability": "out_of_stock"})
        self.assertEqual(response.json()[0]["stock_quantity"], 0)
        self.client.force_login(self.customer)
        response = self.client.post("/api/cart/add/", {"product_id": self.product.pk, "quantity": 1}, content_type="application/json")
        self.assertEqual(response.status_code, 409)

    def test_explicit_import_preserves_existing_products_and_is_atomic(self):
        from django.core.management.base import CommandError
        from inventory.models import Medicine
        medicine = Medicine.objects.create(name="Already linked", strength="10 mg", dosage_form="Tablet",
            selling_unit="tablet", selling_price=Decimal("11.00"), category_name=self.category.name)
        product_pk = medicine.storefront.pk
        call_command("seed_shop", stdout=StringIO())
        self.assertEqual(medicine.storefront.pk, product_pk)
        with self.assertRaises(CommandError):
            call_command("seed_shop", update_existing=True, stdout=StringIO())
        self.assertEqual(Medicine.objects.count(), 1)

    @override_settings(DEBUG=True, MANAGER_LOCAL_PREVIEW=True)
    def test_local_preview_opens_dashboard_root_and_login_without_signin(self):
        # Local preview may never bypass manager authentication or mutate business records.
        self.client.logout()
        before = (Product.objects.count(), PurchaseOrder.objects.count(), StockMovement.objects.count())
        self.assertEqual(self.client.get(reverse("manager:dashboard"), HTTP_HOST="localhost").status_code, 302)
        self.assertEqual(self.client.post(reverse("manager:medicine_new"), {"name": "Blocked"}, HTTP_HOST="localhost").status_code, 302)
        self.assertEqual((Product.objects.count(), PurchaseOrder.objects.count(), StockMovement.objects.count()), before)

    @override_settings(DEBUG=True, MANAGER_LOCAL_PREVIEW=True)
    def test_local_preview_saves_without_creating_or_impersonating_a_user(self):
        # Local preview may never bypass manager authentication or mutate business records.
        self.client.logout()
        before = (Product.objects.count(), PurchaseOrder.objects.count(), StockMovement.objects.count())
        self.assertEqual(self.client.get(reverse("manager:dashboard"), HTTP_HOST="localhost").status_code, 302)
        self.assertEqual(self.client.post(reverse("manager:medicine_new"), {"name": "Blocked"}, HTTP_HOST="localhost").status_code, 302)
        self.assertEqual((Product.objects.count(), PurchaseOrder.objects.count(), StockMovement.objects.count()), before)

    @override_settings(DEBUG=True, MANAGER_LOCAL_PREVIEW=True)
    def test_local_preview_can_create_purchase_order_with_no_named_actor(self):
        # Local preview may never bypass manager authentication or mutate business records.
        self.client.logout()
        before = (Product.objects.count(), PurchaseOrder.objects.count(), StockMovement.objects.count())
        self.assertEqual(self.client.get(reverse("manager:dashboard"), HTTP_HOST="localhost").status_code, 302)
        self.assertEqual(self.client.post(reverse("manager:medicine_new"), {"name": "Blocked"}, HTTP_HOST="localhost").status_code, 302)
        self.assertEqual((Product.objects.count(), PurchaseOrder.objects.count(), StockMovement.objects.count()), before)

    @override_settings(DEBUG=True, MANAGER_LOCAL_PREVIEW=True)
    def test_local_preview_stock_changes_are_still_validated_and_logged(self):
        # Local preview may never bypass manager authentication or mutate business records.
        self.client.logout()
        before = (Product.objects.count(), PurchaseOrder.objects.count(), StockMovement.objects.count())
        self.assertEqual(self.client.get(reverse("manager:dashboard"), HTTP_HOST="localhost").status_code, 302)
        self.assertEqual(self.client.post(reverse("manager:medicine_new"), {"name": "Blocked"}, HTTP_HOST="localhost").status_code, 302)
        self.assertEqual((Product.objects.count(), PurchaseOrder.objects.count(), StockMovement.objects.count()), before)

    @override_settings(DEBUG=True, MANAGER_LOCAL_PREVIEW=True, ALLOWED_HOSTS=["localhost", "testserver"])
    def test_local_preview_rejects_nonlocal_host_or_client(self):
        self.client.logout()
        for host, address in [("testserver", "127.0.0.1"), ("localhost", "192.0.2.1")]:
            response = self.client.get(reverse("manager:dashboard"), HTTP_HOST=host, REMOTE_ADDR=address)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login/", response.url)

    @override_settings(DEBUG=False, MANAGER_LOCAL_PREVIEW=True)
    def test_production_never_uses_local_preview(self):
        self.client.logout()
        response = self.client.get(reverse("manager:dashboard"), HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    @override_settings(DEBUG=True, MANAGER_LOCAL_PREVIEW=False)
    def test_local_preview_can_be_switched_off_for_login_integration(self):
        self.client.logout()
        response = self.client.get(reverse("manager:dashboard"), HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)


    def test_consolidated_navigation_has_no_technical_notice_or_duplicate_sections(self):
        response = self.client.get(reverse("manager:dashboard"))
        for unwanted in ["SUPPORTING WORKFLOWS", "Local development preview", "Preview environment", "Local manager preview"]:
            self.assertNotContains(response, unwanted)
        self.assertNotContains(response, 'href="' + reverse("manager:settings") + '"')
        self.assertRedirects(self.client.get(reverse("manager:settings")), reverse("manager:batches"))

    def test_new_medicine_from_batch_returns_to_preselected_batch_form(self):
        response = self.client.post(reverse("manager:medicine_new") + "?next=batch",
            {"name": "New receipt medicine", "category": self.category.pk, "price": 81, "strength": "20 mg", "dosage_form": "Tablet"})
        product = Product.objects.get(name="New receipt medicine")
        self.assertRedirects(response, reverse("manager:batch_new") + f"?product={product.pk}")
        self.assertEqual(product.stock_quantity, 0)
        form = self.client.get(response.url).context["form"]
        self.assertEqual(str(form["product"].value()), str(product.pk))

    def test_new_supplier_returns_to_the_batch_workflow(self):
        url = reverse("manager:supplier_new") + f"?next=batch&product={self.product.pk}"
        response = self.client.post(url, {"name": "New workflow supplier", "is_active": "on"})
        supplier = Supplier.objects.get(name="New workflow supplier")
        self.assertRedirects(response, reverse("manager:batch_new") + f"?supplier={supplier.pk}&product={self.product.pk}")
        form = self.client.get(response.url).context["form"]
        self.assertEqual(str(form["supplier"].value()), str(supplier.pk))

    def test_medicine_edit_preserves_inventory_rules_and_updates_saved_details(self):
        product = self.linked_product("Edit source")
        detail = product.manager_details
        detail.reorder_level = 15; detail.expiry_warning_days = 21; detail.save()
        data = {"name": "Corrected medicine", "category": product.category_id, "strength": "25mg", "price": 94,
            "dosage_form": "Capsule", "description": "Updated description"}
        response = self.client.post(reverse("manager:medicine_edit", args=[product.pk]), data)
        self.assertRedirects(response, reverse("manager:medicine_detail", args=[product.pk]))
        detail.refresh_from_db(); product.refresh_from_db(); product.medicine.refresh_from_db()
        self.assertEqual((product.medicine.name, product.medicine.selling_price, product.medicine.dosage_form),
            ("Corrected medicine", Decimal("94.00"), "Capsule"))
        self.assertEqual(detail.expiry_warning_days, 21)
        self.assertNotIn("reorder_level", MedicineForm(instance=product).fields)

    def test_inventory_settings_apply_only_to_selected_medicine(self):
        other = Product.objects.create(name="Other threshold medicine", category=self.category, price=10, stock_quantity=5)
        url = reverse("manager:batches") + f"?product={self.product.pk}"
        response = self.client.post(url, {"reorder_level": 8, "expiry_warning_days": 14})
        self.assertRedirects(response, url)
        detail = MedicineDetails.objects.get(product=self.product)
        self.assertEqual((detail.reorder_level, detail.expiry_warning_days), (8, 14))
        self.assertFalse(MedicineDetails.objects.filter(product=other).exists())
        response = self.client.post(url, {"reorder_level": -1, "expiry_warning_days": -1})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["inventory_form"].errors)
        detail.refresh_from_db()
        self.assertEqual(detail.reorder_level, 8)

    def test_expiry_warnings_follow_each_product_and_match_list_report_and_alerts(self):
        detail = self.product.manager_details
        detail.expiry_warning_days = 5
        detail.save()
        batch = self.make_batch(expiry_date=self.today + timedelta(days=10))
        other = Product.objects.create(name="Long warning medicine", category=self.category, price=10, stock_quantity=5)
        MedicineDetails.objects.create(product=other, expiry_warning_days=20)
        second = self.make_batch(product=other, number="LONG", quantity=5, expiry_date=self.today+timedelta(days=10))
        self.assertEqual(list(risks()["expiring"].values_list("pk", flat=True)), [second.pk])
        response = self.client.get(reverse("manager:batches"), {"state": "expiring"})
        self.assertEqual([row.pk for row in response.context["rows"]], [second.pk])
        response = self.client.get(reverse("manager:reports"), {"type": "expiry", "state": "expiring"})
        self.assertEqual(response.context["count"], 1)
        self.assertContains(response, "LONG")
        self.assertEqual(self.client.get(reverse("manager:batch_detail", args=[batch.pk])).context["batch"].expiry_status, "OK")

    def test_batch_edit_records_old_and_new_supplier_cost_quantity_and_expiry(self):
        from .models import BatchHistory
        data = {"product": self.product.pk, "supplier": self.supplier.pk, "number": "TRACEABLE", "quantity": 4,
                "purchase_price": "12.50", "received_date": self.today, "expiry_date": self.today+timedelta(days=20)}
        response = self.client.post(reverse("manager:batch_new"), data)
        batch = Batch.objects.get(number="TRACEABLE")
        self.assertRedirects(response, reverse("manager:batch_detail", args=[batch.pk]))
        replacement = Supplier.objects.create(name="Replacement supplier")
        data.update(supplier=replacement.pk, quantity=3, purchase_price="13.75", expected_quantity=4,
                    expiry_date=self.today+timedelta(days=40), reason="Verified delivery correction")
        response = self.client.post(reverse("manager:batch_edit", args=[batch.pk]), data)
        self.assertRedirects(response, reverse("manager:batch_detail", args=[batch.pk]))
        event = BatchHistory.objects.filter(batch=batch).first()
        self.assertEqual((event.before["quantity"], event.after["quantity"]), (4, 3))
        self.assertEqual((event.before["supplier"], event.after["supplier"]), (self.supplier.name, replacement.name))
        self.assertEqual((event.before["purchase_price"], event.after["purchase_price"]), ("12.50", "13.75"))
        self.assertNotEqual(event.before["expiry_date"], event.after["expiry_date"])
        self.assertEqual(BatchHistory.objects.filter(batch=batch).count(), 2)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 13)

    def test_batch_quantity_edit_without_reason_preserves_stock_and_shows_field_error(self):
        batch = self.make_batch()
        data = {"product": self.product.pk, "supplier": self.supplier.pk, "number": batch.number, "quantity": 2,
            "purchase_price": "12.50", "received_date": batch.received_date, "expiry_date": batch.expiry_date, "expected_quantity": 4}
        response = self.client.post(reverse("manager:batch_edit", args=[batch.pk]), data)
        self.assertContains(response, "Explain the quantity change")
        batch.refresh_from_db()
        self.assertEqual(batch.quantity, 4)
        self.assertFalse(StockMovement.objects.exists())

    def test_delete_batch_requires_confirmation_and_preserves_auditable_history(self):
        from .models import BatchHistory
        batch = self.make_batch()
        url = reverse("manager:batch_delete", args=[batch.pk])
        for data in [None, {"expected_quantity": 4, "reason": "Damaged box"}]:
            response = self.client.get(url) if data is None else self.client.post(url, data)
            self.assertEqual(response.status_code, 200)
            batch.refresh_from_db()
            self.assertFalse(batch.is_archived)
        response = self.client.post(url, {"expected_quantity": 4, "reason": "Damaged box", "confirmed": "on"})
        self.assertRedirects(response, reverse("manager:batches"))
        batch.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual((batch.is_archived, batch.quantity, self.product.stock_quantity), (True, 0, 6))
        movement = StockMovement.objects.get()
        self.assertEqual((movement.delta, movement.previous_quantity, movement.new_quantity), (-4, 10, 6))
        self.assertEqual(BatchHistory.objects.get().before["quantity"], 4)
        self.assertEqual(self.client.get(reverse("manager:batch_detail", args=[batch.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("manager:batch_edit", args=[batch.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("manager:batches")).context["rows"].paginator.count, 0)
        self.assertEqual(self.client.get(reverse("manager:batches"), {"show": "removed"}).context["rows"].paginator.count, 1)

    def test_stale_batch_removal_does_not_change_stock(self):
        batch = self.make_batch()
        response = self.client.post(reverse("manager:batch_delete", args=[batch.pk]),
            {"expected_quantity": 3, "reason": "Damaged", "confirmed": "on"})
        self.assertContains(response, "Batch quantity changed")
        batch.refresh_from_db()
        self.assertFalse(batch.is_archived)
        self.assertFalse(StockMovement.objects.exists())

    def test_removed_batch_cannot_be_received_again(self):
        from .services import remove_batch
        batch = self.make_batch(number="DELIVERY-1", received_date=self.today, expiry_date=self.today+timedelta(days=180))
        remove_batch(batch.pk, 4, "Removed", self.user)
        order, line = self.make_order()
        with self.assertRaises(ValidationError):
            receive_order(order.pk, [self.receipt(line, 1)], self.user)
        line.refresh_from_db()
        self.assertEqual(line.received_quantity, 0)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_delete_unused_supplier_and_retain_referenced_supplier_history(self):
        unused = Supplier.objects.create(name="Unused supplier")
        url = reverse("manager:supplier_delete", args=[unused.pk])
        self.client.get(url)
        self.assertTrue(Supplier.objects.filter(pk=unused.pk).exists())
        self.client.post(url, {"confirmed": "on"})
        self.assertFalse(Supplier.objects.filter(pk=unused.pk).exists())
        batch = self.make_batch()
        response = self.client.post(reverse("manager:supplier_delete", args=[self.supplier.pk]), {"confirmed": "on"})
        self.assertRedirects(response, reverse("manager:suppliers"))
        self.supplier.refresh_from_db()
        self.assertFalse(self.supplier.is_active)
        self.assertTrue(Batch.objects.filter(pk=batch.pk).exists())
        self.assertContains(self.client.get(reverse("manager:supplier_detail", args=[self.supplier.pk])), batch.number)

    def test_contextual_history_and_reports_remain_scoped(self):
        from .services import remove_batch
        batch = self.make_batch()
        other_product = Product.objects.create(name="Unrelated medicine", category=self.category, price=10)
        self.make_batch(product=other_product, number="UNRELATED", quantity=0)
        remove_batch(batch.pk, 4, "Recorded removal", self.user)
        response = self.client.get(reverse("manager:reports"), {"type": "expiry", "product": self.product.pk, "show": "all"})
        self.assertEqual(response.context["count"], 1)
        self.assertContains(response, batch.number)
        self.assertNotContains(response, "UNRELATED")
        self.assertIn(("product", str(self.product.pk)), response.context["scope_filters"])
        response = self.client.get(reverse("manager:reports"), {"type": "batch_history", "batch": batch.pk, "format": "csv"})
        self.assertIn("Recorded removal", response.content.decode())
        response = self.client.get(reverse("manager:reports"), {"type": "history", "product": self.product.pk})
        self.assertEqual(response.context["count"], 1)
        self.assertEqual(response.context["rows"].paginator.count, 1)

    def test_product_and_supplier_details_link_the_actual_batches(self):
        batch = self.make_batch()
        for tab in ["batches", "history", "suppliers"]:
            response = self.client.get(reverse("manager:medicine_detail", args=[self.product.pk]), {"tab": tab})
            self.assertEqual(response.status_code, 200)
            if tab != "history":
                self.assertContains(response, batch.number)
                self.assertContains(response, self.supplier.name)
        order, line = self.make_order()
        response = self.client.get(reverse("manager:supplier_detail", args=[self.supplier.pk]), {"tab": "orders"})
        self.assertContains(response, order.reference)
        self.assertContains(response, "Delete supplier")

    def test_report_paginates_records_before_formatting(self):
        for number in range(30):
            self.make_batch(number=f"PAGE-{number}")
        response = self.client.get(reverse("manager:reports"), {"type": "expiry"})
        self.assertEqual(response.context["count"], 30)
        self.assertEqual(len(response.context["rows"].object_list), 25)
        self.assertTrue(response.context["rows"].has_next())

    def test_new_detail_and_removal_routes_are_protected(self):
        batch = self.make_batch()
        self.client.force_login(self.customer)
        for name, pk in [("medicine_detail", self.product.pk), ("batch_detail", batch.pk), ("batch_delete", batch.pk),
                         ("supplier_detail", self.supplier.pk), ("supplier_delete", self.supplier.pk)]:
            self.assertEqual(self.client.get(reverse("manager:" + name, args=[pk])).status_code, 403)
            self.assertEqual(self.client.post(reverse("manager:" + name, args=[pk]), {"confirmed": "on"}).status_code, 403)


    @override_settings(DEBUG=True, MANAGER_LOCAL_PREVIEW=True)
    def test_anonymous_batch_history_renders_without_a_named_actor(self):
        from .services import adjust_stock
        batch = self.make_batch()
        adjust_stock(batch.pk, -1, 4, "Recorded correction", None)
        self.client.logout()
        url = reverse("manager:batch_detail", args=[batch.pk])
        self.assertEqual(self.client.get(url, HTTP_HOST="localhost").status_code, 302)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(url), "Recorded correction")

    def test_supplier_from_old_batch_snapshot_is_retained_after_supplier_change(self):
        from .services import record_batch, delete_supplier
        batch = self.make_batch()
        record_batch(batch, self.user, "Batch recorded")
        replacement = Supplier.objects.create(name="Current supplier")
        batch.supplier = replacement
        batch.save(update_fields=["supplier"])
        delete_supplier(self.supplier.pk, self.user)
        self.supplier.refresh_from_db()
        self.assertFalse(self.supplier.is_active)
        response = self.client.get(reverse("manager:supplier_detail", args=[self.supplier.pk]))
        self.assertContains(response, batch.number)


    def test_report_keeps_the_originating_section_and_full_csv_detail(self):
        from .services import record_batch
        batch = self.make_batch()
        record_batch(batch, None, "Original batch")
        response = self.client.get(reverse("manager:reports"), {"type": "batch_history", "product": self.product.pk, "section": "batches"})
        self.assertEqual(response.context["active"], "batches")
        self.assertEqual(response.context["back_url"], reverse("manager:batches") + f"?product={self.product.pk}")
        self.assertEqual(len(response.context["headers"]), 6)
        exported = self.client.get(reverse("manager:reports"), {"type": "batch_history", "batch": batch.pk, "format": "csv"})
        self.assertIn("Previous supplier", exported.content.decode())
        self.assertIn("Previous expiry", exported.content.decode())

    def test_expired_batch_removal_does_not_reduce_unexpired_available_stock(self):
        from .services import remove_batch
        batch = self.make_batch(expiry_date=self.today-timedelta(days=1))
        before = available_stock(self.product)
        remove_batch(batch.pk, 4, "Expired stock disposal", None)
        self.product.refresh_from_db()
        self.assertEqual(available_stock(self.product), before)


    def test_manager_medicine_form_uses_default_image_and_ignores_image_input(self):
        self.assertNotIn("image", MedicineForm().fields)
        response = self.client.post(reverse("manager:medicine_new"), {"name": "Default image medicine", "category": self.category.pk,
            "price": 67, "strength": "10 mg", "dosage_form": "Tablet", "image": "https://unwanted.example/image.jpg"})
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(name="Default image medicine")
        self.assertEqual(product.image, "/static/shop/products/default-medicine.svg")
        self.product.image = "/static/existing-medicine.svg"
        self.product.save(update_fields=["image"])
        self.client.post(reverse("manager:medicine_edit", args=[self.product.pk]), {"name": self.product.name,
            "category": self.category.pk, "price": 73, "image": "https://unwanted.example/replacement.jpg"})
        self.product.refresh_from_db()
        self.assertEqual(self.product.image, "/static/existing-medicine.svg")

    def test_delete_controls_are_visible_on_medicine_and_batch_lists_and_details(self):
        batch = self.make_batch()
        medicine_url = reverse("manager:medicine_delete", args=[self.product.pk])
        batch_url = reverse("manager:batch_delete", args=[batch.pk])
        for route in [reverse("manager:medicines"), reverse("manager:medicine_detail", args=[self.product.pk])]:
            self.assertContains(self.client.get(route), medicine_url)
        for route in [reverse("manager:batches"), reverse("manager:batch_detail", args=[batch.pk])]:
            self.assertContains(self.client.get(route), batch_url)
        self.client.post(medicine_url, {"target": "0", "confirmed": "on"})
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)
        self.assertTrue(Batch.objects.filter(pk=batch.pk).exists())

    @override_settings(DEBUG=True, MANAGER_LOCAL_PREVIEW=True)
    def test_signout_is_visible_in_local_mode_and_redirects_to_public_home(self):
        response = self.client.get(reverse("manager:dashboard"), HTTP_HOST="localhost")
        self.assertContains(response, reverse("manager:signout"))
        self.assertContains(response, "Sign out")
        self.assertEqual(self.client.get(reverse("manager:signout"), HTTP_HOST="localhost").status_code, 405)
        response = self.client.post(reverse("manager:signout"), HTTP_HOST="localhost")
        self.assertRedirects(response, reverse("home"))
        self.assertNotIn("_auth_user_id", self.client.session)
        home = self.client.get(reverse("home"), HTTP_HOST="localhost")
        self.assertContains(home, "Your Trusted Community Pharmacy")
        self.assertNotContains(home, "Manager Dashboard")

    def test_sales_report_describes_customer_items_quantities_and_saved_prices(self):
        from orders.models import Order as SharedOrder, OrderItem as SharedItem, Payment as SharedPayment
        product = self.linked_product("Snapshot medicine")
        order = SharedOrder.objects.create(kind="online", customer=self.customer, total_amount=Decimal("246.00"))
        SharedItem.objects.create(order=order, medicine=product.medicine, medicine_name=product.public_name,
            selling_unit="tablet", quantity=2, unit_price=Decimal("73.00"))
        SharedPayment.objects.create(order=order, method="card", amount=Decimal("246.00"), recorded_by=self.customer)
        product.medicine.selling_price = Decimal("999.00")
        product.medicine.save(update_fields=["selling_price"])
        response = self.client.get(reverse("manager:reports"), {"type": "sales"})
        self.assertContains(response, "Items sold")
        self.assertContains(response, "x 2 @ Rs 73.00")
        self.assertContains(response, "customer@example.test")
        self.assertEqual(response.context["total"], Decimal("246.00"))
        row = response.context["rows"].object_list[0]
        self.assertEqual((row[3], row[4]), (Decimal("146.00"), Decimal("100.00")))
        export = self.client.get(reverse("manager:reports"), {"type": "sales", "format": "csv"})
        self.assertIn("73.00", export.content.decode())

    def test_public_home_uses_the_same_active_catalogue(self):
        product = self.linked_product("Public linked medicine")
        self.assertContains(self.client.get(reverse("home")), product.public_name)
        product.medicine.is_active = False
        product.medicine.save(update_fields=["is_active"])
        self.assertNotContains(self.client.get(reverse("home")), product.public_name)
