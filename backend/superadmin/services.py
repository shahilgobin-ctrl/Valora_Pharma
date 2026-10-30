import ipaddress
from django.core.exceptions import ValidationError
from .models import AuditLog, Role

def audit(request, action, target, details=None):
    try:
        ip = str(ipaddress.ip_address(request.META.get("REMOTE_ADDR", "")))
    except ValueError:
        ip = None
    return AuditLog.objects.create(actor=request.user, actor_email=request.user.email, action=action, target=str(target), details=details or {}, ip_address=ip)

def role_for(user):
    if user.is_superuser:
        return "Super Administrator"
    names = {group.name for group in user.groups.all()}
    for name in ("Pharmacy Managers", "Pharmacist", "Customer"):
        if name in names:
            return "Pharmacy Manager" if name == "Pharmacy Managers" else name
    return "Customer" if user.account_type == "customer" else "Staff (unassigned)"

def protect_administrator(actor, target, role, active):
    if target.pk == actor.pk and (role.key != "super-administrator" or not active):
        raise ValidationError("You cannot deactivate your own account or remove your own administrator role.")

def assign_role(user, role):
    user.account_type = "customer" if role.key == "customer" else "admin" if role.key == "super-administrator" else "staff"
    user.is_superuser = role.key == "super-administrator"
    user.is_staff = user.is_superuser
    user.save()
    managed_ids = list(Role.objects.values_list("group_id", flat=True))
    user.groups.remove(*managed_ids)
    user.groups.add(role.group)
