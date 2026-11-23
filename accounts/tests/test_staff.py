import pytest
from django.core.management import call_command

from accounts.models import User
from conftest import PASSWORD

pytestmark = pytest.mark.django_db
S = "/api/v1/staff"


def test_staff_login_rejects_traveler(api, user):
    r = api.post(f"{S}/auth/login", {"email": user.email, "password": PASSWORD}, format="json")
    assert r.status_code == 403


def test_staff_login_sets_staff_cookie(api, admin_user):
    r = api.post(f"{S}/auth/login", {"email": admin_user.email, "password": PASSWORD}, format="json")
    assert r.status_code == 200 and r.json()["user"]["permissions"] == ["admin"]
    c = r.cookies["ar_staff_refresh"]
    assert c["httponly"] and c["path"] == "/api/v1/staff/auth/"


def test_staff_refresh_requires_csrf(api_enforce_csrf, marketing_user):
    c = api_enforce_csrf
    c.post(f"{S}/auth/login", {"email": marketing_user.email, "password": PASSWORD}, format="json")
    assert c.post(f"{S}/auth/refresh").status_code == 403
    token = c.get("/api/v1/auth/csrf").json()["csrfToken"]
    assert c.post(f"{S}/auth/refresh", HTTP_X_CSRFTOKEN=token).status_code == 200


def test_traveler_token_cannot_use_staff_api(auth_api):
    assert auth_api.get(f"{S}/users").status_code == 403


def test_marketing_cannot_manage_users(marketing_api):
    assert marketing_api.get(f"{S}/users").status_code == 403


def test_admin_lists_and_searches_users(admin_api, user, marketing_user):
    r = admin_api.get(f"{S}/users", {"search": "marketing"})
    assert r.status_code == 200
    assert [u["email"] for u in r.json()["results"]] == ["marketing@example.com"]


def test_admin_creates_marketing_user(admin_api):
    r = admin_api.post(f"{S}/users", {"first_name": "M", "last_name": "K", "email": "New@Example.com", "password": "long-enough-pass", "permissions": ["marketing"]}, format="json")
    assert r.status_code == 201, r.content
    u = User.objects.get(email="new@example.com")
    assert u.permissions == ["marketing"] and u.password.startswith("argon2")
    assert "password" not in r.json()


def test_admin_updates_permissions(admin_api, marketing_user):
    r = admin_api.patch(f"{S}/users/{marketing_user.id}", {"permissions": ["admin", "marketing"]}, format="json")
    assert r.status_code == 200
    marketing_user.refresh_from_db()
    assert marketing_user.permissions == ["admin", "marketing"]


def test_admin_soft_deletes_user(admin_api, user):
    assert admin_api.delete(f"{S}/users/{user.id}").status_code == 204
    assert User.all_objects.get(pk=user.pk).deleted_at is not None


def test_create_staff_command(db):
    call_command("create_staff", email="Boss@Example.com", password="long-enough-pass", admin=True)
    u = User.objects.get(email="boss@example.com")
    assert u.permissions == ["admin"] and u.check_password("long-enough-pass")
