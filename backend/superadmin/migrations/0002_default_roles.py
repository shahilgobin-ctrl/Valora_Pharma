from django.db import migrations

ROLE_PERMISSIONS = [
    ("customer", "Customer", [
        ("browse_catalogue", "Browse medicine catalogue"),
        ("manage_cart", "Add medicines to cart"),
        ("upload_prescriptions", "Upload prescriptions"),
        ("view_prescription_status", "View prescription approval status"),
        ("track_orders", "Track order status in real time"),
        ("download_receipts", "Download receipts for completed orders"),
    ]),
    ("pharmacist", "Pharmacist", [
        ("review_prescriptions", "View prescription review queue"),
        ("approve_prescriptions", "Approve or reject prescriptions"),
        ("update_orders", "Update online order status"),
        ("record_sales", "Record walk-in sales via POS"),
        ("view_customer_orders", "View customer order details"),
        ("bulk_dispensing", "Process high-volume dispensing"),
    ]),
    ("pharmacy-manager", "Pharmacy Managers", [
        ("manage_medicines", "Add, edit and archive medicines"),
        ("manage_batches", "Manage medicine batches"),
        ("adjust_stock", "Record stock adjustments"),
        ("manage_suppliers", "Manage Mauritian supplier info"),
        ("create_purchase_orders", "Create purchase orders"),
        ("view_reports", "Generate sales and inventory reports"),
    ]),
    ("super-administrator", "Super Administrator", []),
]

def seed(apps, schema_editor):
    alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Role = apps.get_model("superadmin", "Role")
    User = apps.get_model("accounts", "User")
    Settings = apps.get_model("superadmin", "SystemSettings")
    content_type, _ = ContentType.objects.using(alias).get_or_create(app_label="superadmin", model="role")
    for key, title, definitions in ROLE_PERMISSIONS:
        group, _ = Group.objects.using(alias).get_or_create(name=title)
        Role.objects.using(alias).get_or_create(key=key, defaults={"title": "Pharmacy Manager" if key == "pharmacy-manager" else title, "group": group})
        for code, name in definitions:
            permission, _ = Permission.objects.using(alias).get_or_create(content_type=content_type, codename=code, defaults={"name": name})
            group.permissions.add(permission)
        if key == "customer":
            for user in User.objects.using(alias).filter(account_type="customer", is_superuser=False).iterator():
                user.groups.add(group)
        if key == "super-administrator":
            for user in User.objects.using(alias).filter(is_superuser=True).iterator():
                user.groups.add(group)
    Settings.objects.using(alias).get_or_create(pk=1)

class Migration(migrations.Migration):
    dependencies = [("superadmin", "0001_initial"), ("manager", "0002_manager_access_and_policy")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
