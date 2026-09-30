from django.urls import path
from . import views

app_name = "shop"
urlpatterns = [
    path("shop/", views.shop_page, name="shop"),
    path("shop/<slug:slug>/", views.product_page, name="product"),
    path("cart/", views.cart_page, name="cart"),
    path("api/products/", views.api_products, name="api_products"),
    path("api/products/<slug:slug>/", views.api_product_detail, name="api_product"),
    path("api/categories/", views.api_categories, name="api_categories"),
    path("api/cart/", views.api_cart, name="api_cart"),
    path("api/cart/add/", views.api_cart_add, name="api_cart_add"),
    path("api/cart/remove/", views.api_cart_remove, name="api_cart_remove"),
    path("api/cart/update/", views.api_cart_update, name="api_cart_update"),
    path("api/checkout/", views.api_checkout, name="api_checkout"),
]
