from django.contrib import admin

from .models import HomepageProductImage


@admin.register(HomepageProductImage)
class HomepageProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "image")
    search_fields = ("product__name",)
    autocomplete_fields = ("product",)
