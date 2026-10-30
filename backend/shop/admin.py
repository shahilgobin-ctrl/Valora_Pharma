from pathlib import Path

from django.contrib import admin
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html

from .models import Cart, CartItem, Category, Order, OrderItem, Payment, Product, ShopSettings


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "display_order", "image")
    list_editable = ("display_order",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "medicine", "category", "public_price", "available_stock", "homepage_order")
    readonly_fields = ("name", "description", "strength", "price", "stock_quantity", "is_prescription", "is_active")
    list_filter = ("category", "is_prescription", "is_active")
    search_fields = ("name", "description", "strength")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    list_display = ("id", "user", "total", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("id", "user__username", "user__email")
    readonly_fields = ("created_at", "prescription_download")
    exclude = ("prescription_file",)

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/prescription/",
                self.admin_site.admin_view(self.download_prescription),
                name="shop_order_prescription",
            )
        ]
        return custom_urls + super().get_urls()

    def prescription_download(self, order):
        if not order or not order.prescription_file:
            return "No prescription uploaded"
        url = reverse("admin:shop_order_prescription", args=(order.pk,))
        return format_html('<a href="{}">Download prescription</a>', url)

    prescription_download.short_description = "Prescription document"

    def download_prescription(self, request, object_id):
        order = get_object_or_404(Order, pk=object_id)
        if not order.prescription_file:
            raise Http404("No prescription was uploaded for this order.")
        return FileResponse(
            order.prescription_file.open("rb"),
            as_attachment=True,
            filename=Path(order.prescription_file.name).name,
        )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    list_display = ("id", "order", "status", "amount_total", "amount_paid", "created_at", "paid_at")
    list_filter = ("status", "created_at")
    search_fields = ("order__id", "order__user__username", "order__user__email")


admin.site.register((Cart, CartItem))


@admin.register(ShopSettings)
class ShopSettingsAdmin(admin.ModelAdmin):
    fields = ("delivery_fee", "hero_image")

    def has_add_permission(self, request):
        return not ShopSettings.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False
