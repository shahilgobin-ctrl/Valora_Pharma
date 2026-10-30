from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models

class Role(models.Model):
    key = models.SlugField(unique=True)
    group = models.OneToOneField(Group, on_delete=models.PROTECT, related_name="portal_role")
    title = models.CharField(max_length=80)

    class Meta:
        default_permissions = ()
        permissions = [
            ("browse_catalogue", "Browse medicine catalogue"),
            ("manage_cart", "Add medicines to cart"),
            ("upload_prescriptions", "Upload prescriptions"),
            ("view_prescription_status", "View prescription approval status"),
            ("track_orders", "Track order status in real time"),
            ("download_receipts", "Download receipts for completed orders"),
            ("review_prescriptions", "View prescription review queue"),
            ("approve_prescriptions", "Approve or reject prescriptions"),
            ("update_orders", "Update online order status"),
            ("record_sales", "Record walk-in sales via POS"),
            ("view_customer_orders", "View customer order details"),
            ("bulk_dispensing", "Process high-volume dispensing"),
            ("manage_medicines", "Add, edit and archive medicines"),
            ("manage_batches", "Manage medicine batches"),
            ("adjust_stock", "Record stock adjustments"),
            ("manage_suppliers", "Manage Mauritian supplier info"),
            ("create_purchase_orders", "Create purchase orders"),
            ("view_reports", "Generate sales and inventory reports"),
        ]

    def __str__(self):
        return self.title

class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_email = models.EmailField()
    action = models.CharField(max_length=60)
    target = models.CharField(max_length=254)
    details = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        default_permissions = ("view",)

class SystemSettings(models.Model):
    portal_name = models.CharField(max_length=60, default="ValoraPharma")
    support_email = models.EmailField(blank=True)
    page_size = models.PositiveSmallIntegerField(default=10, choices=[(10, "10"), (25, "25"), (50, "50")])
    customer_registration = models.BooleanField(default=True)
    staff_registration = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls):
        return cls.objects.get_or_create(pk=1)[0]
