from django.urls import path
from . import views

app_name = "accounts"
urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("staff/login/", views.login_view, {"staff": True}, name="staff_login"),
    path("staff/register/", views.register_view, {"staff": True}, name="staff_register"),
    path("logout/", views.logout_view, name="logout"),
]
