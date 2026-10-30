from django.contrib import admin
from django.urls import include, path
from pages.views import home

urlpatterns = [
    path("", home, name="home"),
    path("pharmacist/", include("pharmacist.urls")),
    path("manager/", include("manager.urls")),
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("shop.urls")),
    path("", include("pages.urls")),
]
