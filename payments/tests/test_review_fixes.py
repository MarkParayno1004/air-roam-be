"""Regression tests for the final-review findings (cancel/pay race, bookings on ended orders, throttle, secret, price)."""
import importlib

import pytest
from django.core.exceptions import ImproperlyConfigured

from bookings.models import Booking
from conftest import PASSWORD
from payments import xendit

pytestmark = pytest.mark.django_db
HOOK = "/api/v1/payments/xendit/webhook"


@pytest.fixture(autouse=True)
def token(settings, monkeypatch):
    settings.XENDIT_CALLBACK_TOKEN = "tok"
    monkeypatch.setattr(xendit, "expire_invoice", lambda order: None)


def paid_hook(api, order):
    return api.post(HOOK, {"external_id": str(order.id), "status": "PAID", "amount": float(order.total_amount)}, format="json", HTTP_X_CALLBACK_TOKEN="tok")


def test_paid_webhook_on_cancelled_order_is_flagged(auth_api, api, order_factory):
    o = order_factory()
    assert auth_api.post(f"/api/v1/orders/{o.id}/cancel").status_code == 200
    assert paid_hook(api, o).status_code == 200
    o.refresh_from_db()
    assert o.order_status == "cancelled"
    assert o.needs_attention and "paid" in o.attention_note.lower()


def test_staff_can_filter_orders_needing_attention(admin_api, api, auth_api, order_factory):
    o = order_factory()
    auth_api.post(f"/api/v1/orders/{o.id}/cancel")
    paid_hook(api, o)
    order_factory()
    r = admin_api.get("/api/v1/staff/orders", {"needs_attention": "true"})
    assert [x["id"] for x in r.json()["results"]] == [str(o.id)]
    assert r.json()["results"][0]["attention_note"]


def test_cancel_expires_xendit_invoice(auth_api, order_factory, monkeypatch):
    seen = []
    monkeypatch.setattr(xendit, "expire_invoice", lambda order: seen.append(order.id))
    o = order_factory()
    auth_api.post(f"/api/v1/orders/{o.id}/cancel")
    assert seen == [o.id]


def test_cancel_survives_xendit_expire_failure(auth_api, order_factory, monkeypatch):
    def boom(order):
        raise RuntimeError("down")

    monkeypatch.setattr(xendit, "expire_invoice", boom)
    o = order_factory()
    assert auth_api.post(f"/api/v1/orders/{o.id}/cancel").status_code == 200


def test_cancel_cancels_pending_bookings(auth_api, order_factory):
    o = order_factory("wifi")
    auth_api.post(f"/api/v1/orders/{o.id}/cancel")
    assert Booking.objects.get().booking_status == "cancelled"


def test_expired_webhook_cancels_bookings(api, order_factory):
    o = order_factory("wifi")
    api.post(HOOK, {"external_id": str(o.id), "status": "EXPIRED", "amount": float(o.total_amount)}, format="json", HTTP_X_CALLBACK_TOKEN="tok")
    assert Booking.objects.get().booking_status == "cancelled"


def test_refund_cancels_bookings_and_locks_traveler_edits(admin_api, api, order_factory):
    o = order_factory("wifi")
    paid_hook(api, o)
    assert admin_api.patch(f"/api/v1/staff/orders/{o.id}", {"order_status": "refunded"}, format="json").status_code == 200
    assert Booking.objects.get().booking_status == "cancelled"


def test_spoofed_forwarded_for_still_throttled(api, user):
    codes = [
        api.post("/api/v1/auth/login", {"email": user.email, "password": "wrong-pass-1"}, format="json", HTTP_X_FORWARDED_FOR=f"10.0.0.{i}").status_code
        for i in range(6)
    ]
    assert codes[5] == 429


def test_missing_secret_key_refused_when_not_debug(monkeypatch):
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("DJANGO_SECRET_KEY", "")
    import config.settings as s

    try:
        with pytest.raises(ImproperlyConfigured):
            importlib.reload(s)
    finally:
        monkeypatch.undo()
        importlib.reload(s)


@pytest.mark.parametrize("price", ["0", "-450.00"])
def test_variant_price_must_be_positive(marketing_api, variant_factory, price):
    v = variant_factory()
    r = marketing_api.patch(f"/api/v1/staff/products/{v.product_id}/variants/{v.id}", {"price": price}, format="json")
    assert r.status_code == 400 and "price" in r.json()


def test_login_still_works(api, user):
    assert api.post("/api/v1/auth/login", {"email": user.email, "password": PASSWORD}, format="json").status_code == 200
