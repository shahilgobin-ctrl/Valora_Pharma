from django.contrib import admin
from django.urls import include, path
from .views import start, public_home

urlpatterns = [
    path("", start),
    path("home/", public_home, name="home"),
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("shop.urls")),
    path("manager/", include("manager.urls")),
]
