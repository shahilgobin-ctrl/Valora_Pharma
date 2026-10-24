from django.urls import path
from . import views

app_name = "accounts"
urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("staff/login/", views.login_view, {"staff": True}, name="staff_login"),
    path("staff/register/", views.register_view, {"staff": True}, name="staff_register"),
    path("logout/", views.logout_view, name="logout"),
    path("password/forgot/", views.password_forgot_view, name="password_forgot"),
    path("password/verify/", views.password_verify_view, name="password_verify"),
    path("password/new/", views.password_new_view, name="password_new"),
    path("staff/password/forgot/", views.password_forgot_view, {"staff": True}, name="staff_password_forgot"),
    path("staff/password/verify/", views.password_verify_view, {"staff": True}, name="staff_password_verify"),
    path("staff/password/new/", views.password_new_view, {"staff": True}, name="staff_password_new"),
    path("terms/", views.terms_view, name="terms"),
]
