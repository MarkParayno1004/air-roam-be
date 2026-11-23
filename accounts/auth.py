from django.conf import settings
from rest_framework.authentication import CSRFCheck
from rest_framework.exceptions import PermissionDenied

REFRESH_MAX_AGE = int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())

WEB_COOKIE = ("ar_refresh", "/api/v1/auth/web/")
STAFF_COOKIE = ("ar_staff_refresh", "/api/v1/staff/auth/")


def enforce_csrf(request):
    """Cookie-authenticated endpoints must carry a valid CSRF token (DRF views are csrf-exempt by default)."""
    check = CSRFCheck(lambda req: None)
    django_request = getattr(request, "_request", request)
    check.process_request(django_request)
    reason = check.process_view(django_request, None, (), {})
    if reason:
        raise PermissionDenied("CSRF Failed: CSRF token missing or incorrect.")


def set_refresh_cookie(response, name, path, token):
    response.set_cookie(
        name,
        token,
        max_age=REFRESH_MAX_AGE,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="Strict",
        path=path,
    )


def clear_refresh_cookie(response, name, path):
    response.set_cookie(name, "", max_age=0, httponly=True, secure=settings.COOKIE_SECURE, samesite="Strict", path=path)
