import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from accounts.models import User

pytestmark = pytest.mark.django_db


def test_password_is_argon2():
    u = User.objects.create_user("A@x.com", "correct-horse-1")
    assert u.password.startswith("argon2")
    assert u.email == "a@x.com"


def test_email_unique_case_insensitive():
    User.objects.create_user("a@x.com", "correct-horse-1")
    with pytest.raises(IntegrityError):
        User.objects.create_user("A@X.COM", "correct-horse-1")


def test_permissions_validated():
    u = User(email="b@x.com", first_name="B", last_name="X", permissions=["admin", "root"])
    with pytest.raises(ValidationError):
        u.full_clean(exclude=["password"])


def test_effective_address_prefers_pin_point():
    u = User(address="Makati", pin_point_lat=14.5, pin_point_lng=121.0, pin_point_label="Ayala Ave")
    assert u.effective_address == "Ayala Ave"
    u.pin_point_lng = None
    assert u.effective_address == "Makati"


def test_soft_delete_hides_user():
    u = User.objects.create_user("c@x.com", "correct-horse-1")
    u.soft_delete()
    assert not User.objects.filter(pk=u.pk).exists()
    assert User.all_objects.filter(pk=u.pk).exists()


def test_roles():
    u = User(email="d@x.com", permissions=["marketing"])
    assert u.is_staff_member and u.has_role("marketing") and not u.has_role("admin")
    assert not User(email="e@x.com").is_staff_member
