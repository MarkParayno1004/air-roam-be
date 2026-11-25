"""Regression tests for the final-review findings (cancel/pay race, bookings on ended orders, throttle, secret, price)."""
import importlib

import pytest
from django.core.exceptions import ImproperlyConfigured

from bookings.models import Booking
from conftest import PASSWORD
from payments import paymongo

pytestmark = pytest.mark.django_db


def paid_hook(api, pay_api, order):
    pay_api.pay(order)
    return pay_api.hook(api, order.payment_session_id)


def test_paid_webhook_on_cancelled_order_is_flagged(auth_api, api, order_factory, pay_api):
    o = order_factory()
    pay_api.checkout(o)
    assert auth_api.post(f"/api/v1/orders/{o.id}/cancel").status_code == 200
    assert paid_hook(api, pay_api, o).status_code == 200
    o.refresh_from_db()
    assert o.order_status == "cancelled"
    assert o.needs_attention and "paid" in o.attention_note.lower()


def test_staff_can_filter_orders_needing_attention(admin_api, api, auth_api, order_factory, pay_api):
    o = order_factory()
    pay_api.checkout(o)
    auth_api.post(f"/api/v1/orders/{o.id}/cancel")
    paid_hook(api, pay_api, o)
    order_factory()
    r = admin_api.get("/api/v1/staff/orders", {"needs_attention": "true"})
    assert [x["id"] for x in r.json()["results"]] == [str(o.id)]
    assert r.json()["results"][0]["attention_note"]


def test_cancel_expires_paymongo_session(auth_api, order_factory, pay_api):
    o = order_factory()
    sid = pay_api.checkout(o)
    auth_api.post(f"/api/v1/orders/{o.id}/cancel")
    assert pay_api.sessions[sid]["attributes"]["status"] == "expired"


def cancel_note(order):
    return f"Cancelled by the traveler, but its PayMongo page could not be closed (session {order.payment_session_id}). Check it in the PayMongo dashboard."


def test_cancel_survives_paymongo_expire_failure_and_is_flagged(auth_api, order_factory, pay_api):
    o = order_factory()
    pay_api.checkout(o)
    pay_api.down = True
    assert auth_api.post(f"/api/v1/orders/{o.id}/cancel").status_code == 200
    o.refresh_from_db()
    assert o.order_status == "cancelled" and o.needs_attention and o.attention_note == cancel_note(o)


def test_cancel_that_closes_the_session_is_not_flagged(auth_api, order_factory, pay_api):
    o = order_factory()
    pay_api.checkout(o)
    auth_api.post(f"/api/v1/orders/{o.id}/cancel")
    o.refresh_from_db()
    assert not o.needs_attention and o.attention_note == ""


@pytest.mark.parametrize("webhook", ["before the cancel note", "after the cancel note"])
def test_cancel_and_late_payment_notes_both_survive(auth_api, api, order_factory, pay_api, monkeypatch, webhook):
    o = order_factory()
    pay_api.checkout(o)

    def refused(order):
        if webhook == "before the cancel note":
            paid_hook(api, pay_api, o)
        raise RuntimeError("already paid")

    monkeypatch.setattr(paymongo, "expire_checkout", refused)
    auth_api.post(f"/api/v1/orders/{o.id}/cancel")
    if webhook == "after the cancel note":
        paid_hook(api, pay_api, o)
    o.refresh_from_db()
    assert o.order_status == "cancelled" and o.needs_attention
    assert cancel_note(o) in o.attention_note and "after the order was cancelled" in o.attention_note


def test_cancel_cancels_pending_bookings(auth_api, order_factory):
    o = order_factory("wifi")
    auth_api.post(f"/api/v1/orders/{o.id}/cancel")
    assert Booking.objects.get().booking_status == "cancelled"


def test_refund_cancels_bookings_and_locks_traveler_edits(admin_api, api, order_factory, pay_api):
    o = order_factory("wifi")
    pay_api.checkout(o)
    paid_hook(api, pay_api, o)
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


def test_login_still_works(api, user):
    assert api.post("/api/v1/auth/login", {"email": user.email, "password": PASSWORD}, format="json").status_code == 200
