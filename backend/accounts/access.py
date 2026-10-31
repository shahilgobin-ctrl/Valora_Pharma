"""Shared role checks for pharmacy pages contributed by other Django apps."""

from functools import wraps

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse

from .models import User


def user_has_role(user, *roles):
    if not user.is_authenticated or not user.is_active or user.account_type not in roles:
        return False
    if user.account_type == User.AccountType.ADMIN:
        return user.is_superuser and user.is_staff
    return True


def role_home_name(user):
    if not user.is_authenticated or not user.is_active:
        return None
    if (user.account_type == User.AccountType.STAFF
            and user.groups.filter(name="Pharmacist").exists()):
        return "pharmacist:dashboard"
    if (user.account_type == User.AccountType.STAFF
            and user.has_perm("manager.access_manager")):
        return "manager:dashboard"
    if user.account_type == User.AccountType.ADMIN and not user_has_role(user, User.AccountType.ADMIN):
        return None
    if user.account_type == User.AccountType.ADMIN:
        return "superadmin:overview"
    if (user.account_type == User.AccountType.CUSTOMER
            and settings.PHARMACY_ROLE_HOME_ROUTES.get(user.account_type) == "accounts:customer_landing"):
        try:
            reverse("home")
        except NoReverseMatch:
            pass
        else:
            return "home"
    return settings.PHARMACY_ROLE_HOME_ROUTES.get(user.account_type)


def pharmacy_role_required(*roles):
    """Protect a page by the account role on every request, not just at login."""
    if not roles:
        raise ValueError("At least one pharmacy role is required.")

    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("accounts:login")
            if not request.user.is_active:
                logout(request)
                return redirect("accounts:login")
            if not user_has_role(request.user, *roles):
                return HttpResponseForbidden("This page is not available for your account.")
            return view(request, *args, **kwargs)

        return wrapped

    return decorate
