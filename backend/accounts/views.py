from django.contrib import messages
from django.contrib.auth import login, logout
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from .forms import LoginForm, RegistrationForm
from .models import User
from .rate_limit import (
    is_limited,
    key_for_request,
    record_failure,
    reset_failures,
)


def flow_context(request, staff):
    account_type = (
        User.AccountType.STAFF if staff else User.AccountType.CUSTOMER
    )
    return {
        "is_staff_flow": staff,
        "authenticated": (
            request.user.is_authenticated
            and request.user.account_type == account_type
        ),
        "login_url": reverse(
            "accounts:staff_login" if staff else "accounts:login"
        ),
        "register_url": reverse(
            "accounts:staff_register" if staff else "accounts:register"
        ),
    }


@never_cache
@require_http_methods(["GET", "POST"])
def login_view(request, staff=False):
    account_type = (
        User.AccountType.STAFF if staff else User.AccountType.CUSTOMER
    )
    key = key_for_request(request, account_type)
    blocked = request.method == "POST" and is_limited(key)

    form = LoginForm(
        request.POST if request.method == "POST" else None,
        request=request,
        account_type=account_type,
        blocked=blocked,
    )
    response_status = 429 if blocked else 200

    if request.method == "POST":
        if form.is_valid():
            reset_failures(key)
            login(request, form.user)

            # Pharmacist integration: redirect to the protected dashboard.
            if (
                form.user.is_active
                and form.user.account_type == User.AccountType.STAFF
                and form.user.groups.filter(name="Pharmacist").exists()
            ):
                return redirect("pharmacist:dashboard")

            # Preserve the existing destination for other account roles.
            return redirect(
                "accounts:staff_login" if staff else "accounts:login"
            )

        if not blocked:
            record_failure(key)

    context = flow_context(request, staff)
    context["form"] = form
    return render(
        request,
        "accounts/login.html",
        context,
        status=response_status,
    )


@never_cache
@require_http_methods(["GET", "POST"])
def register_view(request, staff=False):
    form = RegistrationForm(
        request.POST if request.method == "POST" else None
    )

    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save(commit=False)
                user.account_type = (
                    User.AccountType.STAFF
                    if staff
                    else User.AccountType.CUSTOMER
                )
                user.is_active = not staff
                user.is_staff = False
                user.is_superuser = False
                user.save()
        except IntegrityError:
            # The database catches two registrations arriving at once.
            form.add_error(
                "email",
                "An account with this email already exists.",
            )
        else:
            if staff:
                messages.success(
                    request,
                    "Your staff registration was submitted. "
                    "An administrator must approve your account "
                    "before you can sign in.",
                )
            else:
                messages.success(
                    request,
                    "Your account is ready. "
                    "Sign in with your email and password.",
                )

            return redirect(
                "accounts:staff_login" if staff else "accounts:login"
            )

    context = flow_context(request, staff)
    context["form"] = form
    return render(request, "accounts/register.html", context)


@require_POST
def logout_view(request):
    staff = (
        request.user.is_authenticated
        and request.user.account_type == User.AccountType.STAFF
    )
    logout(request)
    messages.success(request, "You have signed out.")
    return redirect(
        "accounts:staff_login" if staff else "accounts:login"
    )