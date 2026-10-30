from functools import wraps
from urllib.parse import urlsplit

from django.conf import settings

from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden
from django.urls import reverse
from django.views.decorators.cache import never_cache


def is_manager(user):
    return (user.is_authenticated and user.is_active
            and (user.is_superuser or user.account_type in {"staff", "admin"})
            and user.has_perm("manager.access_manager"))


def local_preview_allowed(request):
    return (
        settings.DEBUG and settings.MANAGER_LOCAL_PREVIEW
        and request.META.get("REMOTE_ADDR") in {"127.0.0.1", "::1"}
        and urlsplit("//" + request.get_host()).hostname in {"localhost", "127.0.0.1", "::1"}
    )


def manager_required(view):
    @never_cache
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if local_preview_allowed(request):
            request.manager_local_preview = True
            return view(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url=reverse("accounts:login"))
        if not is_manager(request.user):
            return HttpResponseForbidden("This workspace requires Pharmacy Manager access.")
        return view(request, *args, **kwargs)
    return wrapped
