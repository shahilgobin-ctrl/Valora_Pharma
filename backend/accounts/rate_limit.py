"""Small cache-based limit for repeated failed login attempts."""
import hashlib
from django.conf import settings
from django.core.cache import cache

def key_for_request(request, account_type):
    # Use the server's address. Never trust a client-supplied X-Forwarded-For.
    identifier = f"{account_type}:{request.META.get('REMOTE_ADDR', 'unknown')}"
    return "login-failures:" + hashlib.sha256(identifier.encode()).hexdigest()

def is_limited(key):
    return cache.get(key, 0) >= settings.LOGIN_MAX_FAILURES

def record_failure(key):
    if cache.add(key, 1, timeout=settings.LOGIN_LOCKOUT_SECONDS):
        return
    try:
        cache.incr(key)
    except ValueError:  # The entry may have expired between add() and incr().
        cache.add(key, 1, timeout=settings.LOGIN_LOCKOUT_SECONDS)

def reset_failures(key):
    cache.delete(key)
