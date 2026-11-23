import pytest

from accounts.models import User
from conftest import PASSWORD

pytestmark = pytest.mark.django_db

V1 = "/api/v1"
NEW = {"first_name": "Mia", "last_name": "Cruz", "email": "Mia@Example.com", "contact_no": "+639170000000", "password": "long-enough-pass"}


def test_register_creates_traveler_with_no_permissions(api):
    r = api.post(f"{V1}/auth/register", {**NEW, "permissions": ["admin"]}, format="json")
    assert r.status_code == 201, r.content
    u = User.objects.get(email="mia@example.com")
    assert u.permissions == [] and r.json()["permissions"] == []
    assert "password" not in r.json()


def test_register_rejects_short_password(api):
    r = api.post(f"{V1}/auth/register", {**NEW, "password": "short12"}, format="json")
    assert r.status_code == 400 and "password" in r.json()


def test_mobile_login_refresh_logout(api, user):
    r = api.post(f"{V1}/auth/login", {"email": user.email, "password": PASSWORD}, format="json")
    assert r.status_code == 200
    access, refresh = r.json()["access"], r.json()["refresh"]
    assert access and refresh
    r2 = api.post(f"{V1}/auth/refresh", {"refresh": refresh}, format="json")
    assert r2.status_code == 200 and r2.json()["refresh"] != refresh
    new_refresh = r2.json()["refresh"]
    assert api.post(f"{V1}/auth/refresh", {"refresh": refresh}, format="json").status_code == 401  # rotated + blacklisted
    assert api.post(f"{V1}/auth/logout", {"refresh": new_refresh}, format="json").status_code == 204
    assert api.post(f"{V1}/auth/refresh", {"refresh": new_refresh}, format="json").status_code == 401


def test_web_login_sets_httponly_cookie(api, user):
    r = api.post(f"{V1}/auth/web/login", {"email": user.email, "password": PASSWORD}, format="json")
    assert r.status_code == 200
    body = r.json()
    assert body["access"] and "refresh" not in body and body["user"]["email"] == user.email
    c = r.cookies["ar_refresh"]
    assert c["httponly"] and c["samesite"] == "Strict" and c["path"] == "/api/v1/auth/web/"


def _web_login(client, user):
    client.post(f"{V1}/auth/web/login", {"email": user.email, "password": PASSWORD}, format="json")


def _csrf(client):
    return client.get(f"{V1}/auth/csrf").json()["csrfToken"]


def test_web_refresh_requires_csrf(api_enforce_csrf, user):
    c = api_enforce_csrf
    _web_login(c, user)
    assert c.post(f"{V1}/auth/web/refresh").status_code == 403
    token = _csrf(c)
    r = c.post(f"{V1}/auth/web/refresh", HTTP_X_CSRFTOKEN=token)
    assert r.status_code == 200 and r.json()["access"]
    assert r.cookies["ar_refresh"].value


def test_web_logout_clears_cookie(api_enforce_csrf, user):
    c = api_enforce_csrf
    _web_login(c, user)
    token = _csrf(c)
    old = c.cookies["ar_refresh"].value
    r = c.post(f"{V1}/auth/web/logout", HTTP_X_CSRFTOKEN=token)
    assert r.status_code == 204
    assert r.cookies["ar_refresh"]["max-age"] == 0
    c.cookies["ar_refresh"] = old
    assert c.post(f"{V1}/auth/web/refresh", HTTP_X_CSRFTOKEN=token).status_code == 401


def test_web_refresh_without_cookie_is_401(api_enforce_csrf):
    token = _csrf(api_enforce_csrf)
    assert api_enforce_csrf.post(f"{V1}/auth/web/refresh", HTTP_X_CSRFTOKEN=token).status_code == 401


def test_me_get_patch_delete(api, auth_api, user):
    r = auth_api.get(f"{V1}/me")
    assert r.status_code == 200 and r.json()["email"] == user.email
    r = auth_api.patch(f"{V1}/me", {"address": "Makati City", "permissions": ["admin"], "email": "x@y.com"}, format="json")
    assert r.status_code == 200
    user.refresh_from_db()
    assert user.address == "Makati City" and user.permissions == [] and user.email == "traveler@example.com"
    assert auth_api.delete(f"{V1}/me").status_code == 204
    assert api.post(f"{V1}/auth/login", {"email": user.email, "password": PASSWORD}, format="json").status_code == 401


def test_deleted_user_access_token_rejected(auth_api, user):
    user.soft_delete()
    assert auth_api.get(f"{V1}/me").status_code == 401


def test_deleted_user_cannot_refresh(api, user):
    refresh = api.post(f"{V1}/auth/login", {"email": user.email, "password": PASSWORD}, format="json").json()["refresh"]
    user.soft_delete()
    assert api.post(f"{V1}/auth/refresh", {"refresh": refresh}, format="json").status_code == 401


def test_login_throttled(api, user):
    codes = [api.post(f"{V1}/auth/login", {"email": user.email, "password": "wrong-pass-1"}, format="json").status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429
