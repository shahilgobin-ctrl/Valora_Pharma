from django.contrib import admin
from .models import Cart, CartItem, Category, Order, OrderItem, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "stock_quantity", "is_prescription", "is_active")
    list_filter = ("category", "is_prescription", "is_active")
    search_fields = ("name", "description", "strength")
    prepopulated_fields = {"slug": ("name",)}


admin.site.register((Cart, CartItem, Order, OrderItem))
