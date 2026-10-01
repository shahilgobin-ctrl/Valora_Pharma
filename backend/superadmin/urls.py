from django.urls import path
from . import views

app_name = "superadmin"
urlpatterns = [
    path("", views.overview, name="overview"),
    path("login/", views.sign_in, name="login"),
    path("logout/", views.sign_out, name="logout"),
    path("users/", views.users, name="users"),
    path("users/create/", views.account_edit, name="user_create"),
    path("users/<int:pk>/", views.account_detail, name="user_detail"),
    path("users/<int:pk>/edit/", views.account_edit, name="user_edit"),
    path("users/<int:pk>/status/", views.account_status, name="user_status"),
    path("users/<int:pk>/role/", views.account_role, name="user_role"),
    path("roles/", views.roles, name="roles"),
    path("roles/<slug:key>/", views.role_edit, name="role_edit"),
    path("audit/", views.audit_log, name="audit"),
    path("audit/export/", views.audit_export, name="audit_export"),
    path("settings/", views.system_settings, name="settings"),
]
