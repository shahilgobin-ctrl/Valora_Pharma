import csv
from functools import wraps
from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST
from accounts.models import User
from accounts.access import user_has_role
from .forms import AccountForm, RolePermissionsForm, SettingsForm
from .models import AuditLog, Role, SystemSettings
from .services import assign_role, audit, protect_administrator, role_for


def administrator(view):
    @wraps(view)
    @never_cache
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), reverse("accounts:login"))
        if not user_has_role(request.user, User.AccountType.ADMIN):
            return render(request, "superadmin/forbidden.html", status=403)
        if request.method == "POST":
            with transaction.atomic():
                # Serialize governance mutations on databases supporting row locks.
                admins = list(User.objects.select_for_update().filter(is_active=True, is_superuser=True).order_by("pk"))
                if request.user.pk not in {user.pk for user in admins}:
                    return render(request, "superadmin/forbidden.html", status=403)
                return view(request, *args, **kwargs)
        return view(request, *args, **kwargs)
    return wrapped


def page(request, template, active, **context):
    context.update(active=active, portal=SystemSettings.current())
    return render(request, "superadmin/" + template, context)


def paginate(request, queryset):
    return Paginator(queryset, SystemSettings.current().page_size).get_page(request.GET.get("page"))


def filtered_users(request):
    users = User.objects.prefetch_related("groups").order_by("date_joined", "pk")
    query = request.GET.get("q", "").strip()
    if query:
        users = users.filter(
            Q(email__icontains=query)
            | Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
    status = request.GET.get("status", "")
    if status in ("active", "inactive"):
        users = users.filter(is_active=status == "active")
    return users


def account_rows(users):
    for user in users:
        user.portal_role = role_for(user)
    return users


@never_cache
@require_http_methods(["GET", "POST"])
def sign_in(request):
    return redirect("accounts:login")


@require_POST
@administrator
def sign_out(request):
    audit(request, "ADMIN_SIGNED_OUT", request.user.email)
    logout(request)
    messages.success(request, "You have been signed out.")
    return redirect("superadmin:login")


@administrator
@require_http_methods(["GET"])
def overview(request):
    accounts = paginate(request, filtered_users(request))
    account_rows(accounts)
    all_users = User.objects.all()
    return page(request, "overview.html", "overview", accounts=accounts, total=all_users.count(), active_count=all_users.filter(is_active=True).count(), inactive_count=all_users.filter(is_active=False).count(), staff_count=all_users.filter(account_type__in=["staff", "admin"]).count())


@administrator
@require_http_methods(["GET"])
def users(request):
    accounts = paginate(request, filtered_users(request))
    account_rows(accounts)
    return page(request, "users.html", "users", accounts=accounts, roles=Role.objects.order_by("pk"))


@administrator
@require_http_methods(["GET"])
def account_detail(request, pk):
    account = get_object_or_404(User.objects.prefetch_related("groups"), pk=pk)
    return page(request, "user_detail.html", "users", account=account, role=role_for(account), permissions=sorted(account.get_all_permissions()), recent=AuditLog.objects.filter(target=account.email)[:8])


@administrator
@require_http_methods(["GET", "POST"])
def account_edit(request, pk=None):
    account = get_object_or_404(User, pk=pk) if pk else User()
    initial_role = Role.objects.filter(title=role_for(account)).first() if pk else Role.objects.get(key="customer")
    form = AccountForm(request.POST if request.method == "POST" else None, instance=account, initial={"role": initial_role})
    before = {
        field: str(getattr(account, field))
        for field in (
            "first_name", "last_name", "email", "username", "phone",
            "date_of_birth", "gender", "is_active",
        )
    }
    previous_role = role_for(account) if pk else None
    if request.method == "POST" and form.is_valid():
        role = form.cleaned_data["role"]
        try:
            protect_administrator(request.user, account, role, form.cleaned_data["is_active"])
            with transaction.atomic():
                account = form.save(commit=False)
                password = form.cleaned_data.get("password")
                if password:
                    account.set_password(password)
                assign_role(account, role)
                changes = {field: {"before": value, "after": str(getattr(account, field))} for field, value in before.items() if value != str(getattr(account, field))}
                audit(request, "USER_UPDATED" if pk else "USER_CREATED", account.email, {"changes": changes, "role_before": previous_role, "role_after": role.title, "password_changed": bool(password)})
                if account.pk == request.user.pk and password:
                    update_session_auth_hash(request, account)
            messages.success(request, "Account updated." if pk else "Account created.")
            return redirect("superadmin:user_detail", pk=account.pk)
        except ValidationError as exc:
            form.add_error(None, exc)
        except IntegrityError:
            form.add_error("email", "An account with this email already exists.")
    return page(request, "user_form.html", "users", form=form, account=account, editing=bool(pk))


@require_POST
@administrator
def account_status(request, pk):
    account = get_object_or_404(User.objects.select_for_update(), pk=pk)
    desired = request.POST.get("active")
    if desired not in ("0", "1"):
        return HttpResponseBadRequest("Choose a valid account status.")
    active = desired == "1"
    if account.pk == request.user.pk and not active:
        messages.error(request, "You cannot deactivate your own account.")
    elif account.is_active != active:
        account.is_active = active
        account.save(update_fields=["is_active"])
        audit(request, "USER_ACTIVATED" if active else "USER_DEACTIVATED", account.email)
        messages.success(request, "Account activated." if active else "Account deactivated.")
    return redirect("superadmin:users")


@require_POST
@administrator
def account_role(request, pk):
    account = get_object_or_404(User.objects.select_for_update(), pk=pk)
    role = get_object_or_404(Role, key=request.POST.get("role", ""))
    previous = role_for(account)
    try:
        protect_administrator(request.user, account, role, account.is_active)
        assign_role(account, role)
        audit(request, "USER_ROLE_CHANGED", account.email, {"before": previous, "after": role.title})
        messages.success(request, "Role updated.")
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    return redirect("superadmin:users")


@administrator
@require_http_methods(["GET"])
def roles(request):
    roles = list(Role.objects.select_related("group").prefetch_related("group__permissions").order_by("pk"))
    for role in roles:
        role.display_permissions = sorted(role.group.permissions.all(), key=lambda permission: permission.pk)
    return page(request, "roles.html", "roles", roles=roles)


@administrator
@require_http_methods(["GET", "POST"])
def role_edit(request, key):
    role = get_object_or_404(Role.objects.select_related("group"), key=key)
    locked = key == "super-administrator"
    form = RolePermissionsForm(request.POST if request.method == "POST" else None, initial={"permissions": role.group.permissions.all()})
    if request.method == "POST":
        if locked:
            return HttpResponseBadRequest("Super Administrator access is fixed and cannot be reduced here.")
        if form.is_valid():
            before = list(role.group.permissions.values_list("codename", flat=True))
            # Preserve unrelated permissions such as manager.access_manager
            # on the shared Pharmacy Managers group.
            other_permissions = role.group.permissions.exclude(
                content_type__app_label="superadmin", content_type__model="role")
            role.group.permissions.set([*other_permissions, *form.cleaned_data["permissions"]])
            audit(request, "ROLE_PERMISSIONS_UPDATED", role.title, {"before": before, "after": list(role.group.permissions.values_list("codename", flat=True))})
            messages.success(request, "Role permissions saved. They apply to all accounts assigned to this role.")
            return redirect("superadmin:roles")
    return page(request, "role_form.html", "roles", role=role, form=form, locked=locked)


def filtered_logs(request):
    logs = AuditLog.objects.all()
    query = request.GET.get("q", "").strip()
    if query:
        logs = logs.filter(Q(actor_email__icontains=query) | Q(target__icontains=query) | Q(action__icontains=query))
    action = request.GET.get("action", "")
    if action:
        logs = logs.filter(action=action)
    return logs


@administrator
@require_http_methods(["GET"])
def audit_log(request):
    return page(request, "audit.html", "audit", logs=paginate(request, filtered_logs(request)), actions=AuditLog.objects.order_by("action").values_list("action", flat=True).distinct())


def csv_safe(value):
    text = str(value or "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text


@administrator
@require_http_methods(["GET"])
def audit_export(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="valora-audit-log.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["Timestamp (Indian/Mauritius)", "User", "Action", "Target", "IP"])
    for entry in filtered_logs(request).iterator():
        writer.writerow([timezone.localtime(entry.created_at).isoformat(), csv_safe(entry.actor_email), entry.action, csv_safe(entry.target), entry.ip_address or ""])
    return response


@administrator
@require_http_methods(["GET", "POST"])
def system_settings(request):
    settings = SystemSettings.current()
    before = {field: getattr(settings, field) for field in SettingsForm.Meta.fields}
    form = SettingsForm(request.POST if request.method == "POST" else None, instance=settings)
    if request.method == "POST" and form.is_valid():
        settings = form.save()
        audit(request, "SYSTEM_SETTINGS_UPDATED", "System settings", {"changes": {field: {"before": old, "after": getattr(settings, field)} for field, old in before.items() if old != getattr(settings, field)}})
        messages.success(request, "System settings saved.")
        return redirect("superadmin:settings")
    return page(request, "settings.html", "settings", form=form)
