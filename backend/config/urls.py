from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="superadmin:overview", permanent=False)),
    path("superadmin/", include("superadmin.urls")),
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
]
