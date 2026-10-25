import hashlib
import logging
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from .forms import (
    LoginForm, PasswordResetNewPasswordForm, PasswordResetRequestForm,
    PasswordResetVerifyForm, RegistrationForm,
)
from .models import PasswordResetChallenge, TERMS_VERSION, User
from .rate_limit import is_limited, key_for_request, record_failure, reset_failures

logger = logging.getLogger(__name__)
RESET_SESSION_KEY = "password_reset_flow"
INVALID_CODE_MESSAGE = "The code is invalid or expired. Request a new code if needed."


def _landing_name(user):
    """Choose a pharmacy area from the verified account role, never a URL parameter."""
    if not user.is_active:
        return None
    return {
        User.AccountType.CUSTOMER: "accounts:customer_landing",
        User.AccountType.STAFF: "accounts:staff_landing",
    }.get(user.account_type)


def _redirect_to_landing(request):
    destination = _landing_name(request.user)
    if destination is None:
        if not request.user.is_active:
            logout(request)
            return redirect("accounts:login")
        return HttpResponseForbidden("This account does not have an assigned pharmacy area.")
    return redirect(destination)


def _landing_view(request, required_role):
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    if not request.user.is_active:
        logout(request)
        return redirect("accounts:login")
    if request.user.account_type != required_role:
        return HttpResponseForbidden("This page is not available for your account.")
    if required_role == User.AccountType.STAFF:
        title = "Staff area"
        message = "Your staff dashboard is coming soon."
    else:
        title = "Customer area"
        message = "Your customer home is coming soon."
    return render(request, "accounts/landing.html", {
        "landing_role": required_role,
        "landing_title": title,
        "landing_message": message,
        "first_name": request.user.first_name or request.user.email,
    })


@never_cache
@require_GET
def customer_landing_view(request):
    return _landing_view(request, User.AccountType.CUSTOMER)


@never_cache
@require_GET
def staff_landing_view(request):
    return _landing_view(request, User.AccountType.STAFF)

def flow_context(request, staff):
    return {
        "is_staff_flow": staff,
        "authenticated": request.user.is_authenticated,
        "login_url": reverse("accounts:login"),
        "register_url": reverse("accounts:staff_register" if staff else "accounts:register"),
        "password_forgot_url": reverse("accounts:password_forgot"),
        "terms_url": reverse("accounts:terms") + ("?from=staff" if staff else ""),
    }

@never_cache
@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return _redirect_to_landing(request)
    key = key_for_request(request, "shared")
    blocked = request.method == "POST" and is_limited(key)
    form = LoginForm(
        request.POST if request.method == "POST" else None,
        request=request, blocked=blocked,
    )
    response_status = 429 if blocked else 200
    if request.method == "POST":
        if form.is_valid():
            reset_failures(key)
            login(request, form.user)
            return _redirect_to_landing(request)
        if not blocked:
            record_failure(key)
    context = flow_context(request, False)
    context["form"] = form
    return render(request, "accounts/login.html", context, status=response_status)


@never_cache
@require_http_methods(["GET", "POST"])
def legacy_staff_login_view(request):
    # Keep old bookmarks/forms working while /login/ is the only sign-in page.
    return redirect("accounts:login", preserve_request=request.method == "POST")

@never_cache
@require_http_methods(["GET", "POST"])
def register_view(request, staff=False):
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save(commit=False)
                user.account_type = User.AccountType.STAFF if staff else User.AccountType.CUSTOMER
                user.is_active = not staff
                user.is_staff = False
                user.is_superuser = False
                user.terms_accepted_at = timezone.now()
                user.terms_version = TERMS_VERSION
                user.save()
        except IntegrityError:
            # The database catches two registrations arriving at once.
            form.add_error("email", "An account with this email already exists.")
        else:
            if staff:
                messages.success(request, "Your staff registration was submitted. An administrator must approve your account before you can sign in.")
            else:
                messages.success(request, "Your account is ready. Sign in with your email and password.")
            return redirect("accounts:login")
    context = flow_context(request, staff)
    context["form"] = form
    return render(request, "accounts/register.html", context)

@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "You have signed out.")
    return redirect("accounts:login")


def _reset_route(stage):
    return reverse("accounts:password_" + stage)


def _code_hash(token, code):
    return salted_hmac("accounts.password-reset-code", f"{token}:{code}").hexdigest()


def _reset_request_allowed(request, email):
    # Apply the same limits before looking up an account, including unknown emails.
    email_key = "password-reset-email:" + hashlib.sha256(email.encode()).hexdigest()
    ip = request.META.get("REMOTE_ADDR", "unknown")
    ip_key = "password-reset-ip:" + hashlib.sha256(ip.encode()).hexdigest()
    if cache.get(ip_key, 0) >= settings.PASSWORD_RESET_IP_LIMIT:
        return False
    if not cache.add(email_key, 1, timeout=settings.PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS):
        return False
    if not cache.add(ip_key, 1, timeout=settings.PASSWORD_RESET_IP_WINDOW_SECONDS):
        try:
            cache.incr(ip_key)
        except ValueError:
            cache.add(ip_key, 1, timeout=settings.PASSWORD_RESET_IP_WINDOW_SECONDS)
    return True


def _reset_flow(request):
    flow = request.session.get(RESET_SESSION_KEY)
    if not isinstance(flow, dict):
        return None
    try:
        uuid.UUID(flow.get("token", ""))
    except (TypeError, ValueError, AttributeError):
        return None
    return flow


def _challenge(request):
    flow = _reset_flow(request)
    if flow is None:
        return None
    return PasswordResetChallenge.objects.select_related("user").filter(token=flow["token"]).first()


def _usable_challenge(challenge, *, verified=False):
    if not challenge:
        return False
    if challenge.consumed_at or challenge.expires_at <= timezone.now():
        return False
    if challenge.attempts >= settings.PASSWORD_RESET_MAX_ATTEMPTS:
        return False
    if (not challenge.user.is_active
            or challenge.user.account_type != challenge.account_type
            or challenge.account_type not in (User.AccountType.CUSTOMER, User.AccountType.STAFF)):
        return False
    return bool(challenge.verified_at) if verified else not challenge.verified_at


@never_cache
@require_http_methods(["GET", "POST"])
def password_forgot_view(request):
    form = PasswordResetRequestForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        old_flow = _reset_flow(request)
        token = (old_flow.get("token") if old_flow and old_flow.get("email") == email
                 else str(uuid.uuid4()))
        if _reset_request_allowed(request, email):
            user = User.objects.filter(
                email__iexact=email, is_active=True,
                account_type__in=(User.AccountType.CUSTOMER, User.AccountType.STAFF),
            ).first()
            if user:
                code = f"{secrets.randbelow(1_000_000):06d}"
                expiry = timezone.now() + timedelta(seconds=settings.PASSWORD_RESET_CODE_TTL_SECONDS)
                challenge = PasswordResetChallenge.objects.create(
                    user=user, account_type=user.account_type, code_hash="", expires_at=expiry,
                )
                challenge.code_hash = _code_hash(challenge.token, code)
                challenge.save(update_fields=["code_hash"])
                try:
                    send_mail(
                        "ValoraPharma password reset code",
                        f"Your ValoraPharma password reset code is {code}. "
                        f"It expires in {settings.PASSWORD_RESET_CODE_TTL_SECONDS // 60} minutes. "
                        "If you did not request this, you can ignore this email.",
                        settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False,
                    )
                except Exception:
                    logger.exception("Password reset email delivery failed")
                    challenge.delete()
                else:
                    PasswordResetChallenge.objects.filter(
                        user=user, consumed_at__isnull=True,
                    ).exclude(pk=challenge.pk).update(consumed_at=timezone.now())
                    token = str(challenge.token)
        request.session[RESET_SESSION_KEY] = {
            "email": email, "token": token, "attempts": 0,
        }
        messages.success(request, "If an eligible account exists, we have sent a verification code to that email address.")
        if _usable_challenge(_challenge(request), verified=True):
            return redirect(_reset_route("new"))
        return redirect(_reset_route("verify"))
    context = flow_context(request, False)
    context.update(form=form, back_url=context["login_url"])
    return render(request, "accounts/password_forgot.html", context)


@never_cache
@require_http_methods(["GET", "POST"])
def password_verify_view(request):
    flow = _reset_flow(request)
    if flow is None:
        return redirect(_reset_route("forgot"))
    challenge = _challenge(request)
    if _usable_challenge(challenge, verified=True):
        return redirect(_reset_route("new"))
    if challenge and not _usable_challenge(challenge):
        request.session.pop(RESET_SESSION_KEY, None)
        messages.error(request, INVALID_CODE_MESSAGE)
        return redirect(_reset_route("forgot"))
    if flow.get("attempts", 0) >= settings.PASSWORD_RESET_MAX_ATTEMPTS:
        request.session.pop(RESET_SESSION_KEY, None)
        messages.error(request, INVALID_CODE_MESSAGE)
        return redirect(_reset_route("forgot"))
    form = PasswordResetVerifyForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        if challenge:
            with transaction.atomic():
                challenge = PasswordResetChallenge.objects.select_for_update().select_related("user").get(pk=challenge.pk)
                if _usable_challenge(challenge) and constant_time_compare(
                    challenge.code_hash, _code_hash(challenge.token, form.cleaned_data["code"]),
                ):
                    challenge.verified_at = timezone.now()
                    challenge.save(update_fields=["verified_at"])
                    return redirect(_reset_route("new"))
                if _usable_challenge(challenge):
                    challenge.attempts += 1
                    challenge.save(update_fields=["attempts"])
        else:
            flow["attempts"] = flow.get("attempts", 0) + 1
            request.session[RESET_SESSION_KEY] = flow
        form.add_error("code", INVALID_CODE_MESSAGE)
    context = flow_context(request, False)
    context.update(form=form, back_url=_reset_route("forgot"))
    return render(request, "accounts/password_verify.html", context)


@never_cache
@require_http_methods(["GET", "POST"])
def password_new_view(request):
    challenge = _challenge(request)
    if not _usable_challenge(challenge, verified=True):
        request.session.pop(RESET_SESSION_KEY, None)
        messages.error(request, "Start password recovery again to set a new password.")
        return redirect(_reset_route("forgot"))
    form = PasswordResetNewPasswordForm(
        request.POST if request.method == "POST" else None, user=challenge.user,
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            locked = PasswordResetChallenge.objects.select_for_update().select_related("user").get(pk=challenge.pk)
            if not _usable_challenge(locked, verified=True):
                request.session.pop(RESET_SESSION_KEY, None)
                messages.error(request, "Start password recovery again to set a new password.")
                return redirect(_reset_route("forgot"))
            locked.user.set_password(form.cleaned_data["new_password1"])
            locked.user.save(update_fields=["password"])
            locked.consumed_at = timezone.now()
            locked.save(update_fields=["consumed_at"])
            PasswordResetChallenge.objects.filter(
                user=locked.user, consumed_at__isnull=True,
            ).exclude(pk=locked.pk).update(consumed_at=timezone.now())
        logout(request)
        messages.success(request, "Your password has been changed. Sign in with your new password.")
        return redirect("accounts:login")
    context = flow_context(request, False)
    context.update(form=form, back_url=_reset_route("forgot"))
    return render(request, "accounts/password_new.html", context)


@never_cache
@require_http_methods(["GET", "POST"])
def legacy_staff_password_forgot_view(request):
    return redirect("accounts:password_forgot", preserve_request=request.method == "POST")


@never_cache
@require_http_methods(["GET", "POST"])
def legacy_staff_password_verify_view(request):
    return redirect("accounts:password_verify", preserve_request=request.method == "POST")


@never_cache
@require_http_methods(["GET", "POST"])
def legacy_staff_password_new_view(request):
    return redirect("accounts:password_new", preserve_request=request.method == "POST")


@never_cache
@require_GET
def terms_view(request):
    staff = request.GET.get("from") == "staff"
    context = flow_context(request, staff)
    context.update(form=None, back_url=context["register_url"], terms_version=TERMS_VERSION)
    return render(request, "accounts/terms.html", context)
