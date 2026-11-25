import json
from datetime import timedelta
from decimal import Decimal

import pytest
import requests
from django.core.management import call_command
from django.utils import timezone

from orders.models import Order
from payments import paymongo

pytestmark = pytest.mark.django_db
HOOK = "/api/v1/payments/paymongo/webhook"


@pytest.fixture(autouse=True)
def urls(settings):
    settings.WEB_STORE_URL = "https://airroam.test"
    settings.APP_DEEP_LINK = "airroam://payment-result"


@pytest.fixture
def order(order_factory, pay_api):
    """Pending 799.00 order with an open checkout session."""
    o = order_factory()
    pay_api.checkout(o)
    return o


def status(order):
    order.refresh_from_db()
    return order.order_status


def saved(order):
    return Order.all_objects.filter(pk=order.pk).values().get()


# Checkout sessions


def test_create_checkout_payload(order_factory, pay_api):
    o = order_factory()
    assert paymongo.create_checkout(o) == ("cs_1", "https://checkout.paymongo.com/cs_1")
    o.refresh_from_db()
    assert (o.payment_session_id, o.payment_url) == ("cs_1", "https://checkout.paymongo.com/cs_1")
    [call] = pay_api.calls
    assert (call["method"], call["url"]) == ("POST", "https://api.paymongo.com/v1/checkout_sessions")
    assert call["auth"] == ("sk_test_abc", "") and call["timeout"] == 10
    name = f"Air Roam order {str(o.id)[:8]}"
    assert call["json"]["data"]["attributes"] == {
        "line_items": [{"name": name, "amount": 79900, "currency": "PHP", "quantity": 1}],
        "payment_method_types": ["gcash", "paymaya", "qrph", "card"],
        "success_url": f"https://airroam.test/payment-result?order_id={o.id}",
        "cancel_url": f"https://airroam.test/account/orders/{o.id}",
        "reference_number": str(o.id),
        "description": name,
    }


def test_create_checkout_app_deep_link(order_factory, pay_api):
    o = order_factory(client="app")
    pay_api.checkout(o)
    sent = pay_api.calls[0]["json"]["data"]["attributes"]
    assert sent["success_url"] == sent["cancel_url"] == f"airroam://payment-result?order_id={o.id}"


@pytest.mark.parametrize("total,centavos", [("299.99", 29999), ("1299.50", 129950), ("0.29", 29), ("1.15", 115), ("9999999999.99", 999999999999)])
def test_centavos_are_exact(api, order, pay_api, total, centavos):
    Order.objects.update(total_amount=Decimal(total))
    order.refresh_from_db()
    pay_api.checkout(order)
    amount = pay_api.calls[-1]["json"]["data"]["attributes"]["line_items"][0]["amount"]
    assert amount == centavos and type(amount) is int
    pay_api.pay(order, centavos)
    assert pay_api.hook(api, order.payment_session_id).status_code == 200
    assert status(order) == "paid" and not order.needs_attention


@pytest.mark.parametrize("how", ["down", "refused"])
def test_create_checkout_raises_on_error(order_factory, pay_api, how):
    pay_api.down, pay_api.fail = how == "down", {"cs_1": 500}
    with pytest.raises(requests.RequestException):
        paymongo.create_checkout(order_factory())


# Webhook: signature


def test_valid_test_signature(api, order, pay_api):
    pay_api.pay(order)
    r = pay_api.hook(api, order.payment_session_id)
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert status(order) == "paid"


def test_valid_live_signature(api, order, pay_api, settings):
    settings.PAYMONGO_SECRET_KEY = "sk_live_abc"
    pay_api.pay(order)
    assert pay_api.hook(api, order.payment_session_id, mode="li").status_code == 200
    assert status(order) == "paid"


@pytest.mark.parametrize("key,mode", [("sk_test_abc", "li"), ("sk_live_abc", "te")])
def test_signature_of_the_other_mode_rejected(api, order, pay_api, settings, key, mode):
    settings.PAYMONGO_SECRET_KEY = key
    pay_api.pay(order)
    assert pay_api.hook(api, order.payment_session_id, mode=mode).status_code == 403
    assert status(order) == "pending_payment"


def test_wrong_secret_rejected_and_logged_without_content(api, order, pay_api, caplog):
    pay_api.pay(order)
    assert pay_api.hook(api, order.payment_session_id, secret="whsk_other").status_code == 403
    assert [(r.levelname, r.getMessage()) for r in caplog.records if r.name == "payments.views"] == [("WARNING", "paymongo webhook rejected: bad signature")]


@pytest.mark.parametrize("secret", ["", "whsk_test"])
def test_no_configured_secret_rejects_everything(api, order, pay_api, settings, secret):
    settings.PAYMONGO_WEBHOOK_SECRET = ""
    pay_api.pay(order)
    assert pay_api.hook(api, order.payment_session_id, secret=secret).status_code == 403
    assert status(order) == "pending_payment"


@pytest.mark.parametrize("header", [None, "", "nonsense", "t=1,te=,li=", "t=1", "te=é", "t=1,te=00,li=00"])
def test_missing_or_bad_signature_header_rejected(api, pay_api, header):
    extra = {} if header is None else {"HTTP_PAYMONGO_SIGNATURE": header}
    assert api.post(HOOK, "{}", content_type="application/json", **extra).status_code == 403
    assert pay_api.calls == []


def signed_header(pay_api, body):
    """The header the fake puts on `body`."""

    class Capture:
        def post(self, url, body, **kw):
            return kw["HTTP_PAYMONGO_SIGNATURE"]

    return pay_api.send(Capture(), body)


def event(session_id):
    return {"data": {"attributes": {"type": "checkout_session.payment.paid", "data": {"id": session_id}}}}


def test_tampered_body_rejected(api, order, pay_api):
    pay_api.pay(order)
    header = signed_header(pay_api, json.dumps(event("cs_other")))
    r = api.post(HOOK, json.dumps(event("cs_1")), content_type="application/json", HTTP_PAYMONGO_SIGNATURE=header)
    assert r.status_code == 403 and status(order) == "pending_payment"


def test_signature_covers_the_body_exactly_as_sent(api, order, pay_api):
    pay_api.pay(order)
    body = "\n " + json.dumps({**event("cs_1"), "note": "₱ é"}, indent=3, ensure_ascii=False) + "\n"
    header = signed_header(pay_api, body)
    compact = json.dumps(json.loads(body))  # same JSON, other bytes
    assert api.post(HOOK, compact, content_type="application/json", HTTP_PAYMONGO_SIGNATURE=header).status_code == 403
    assert api.post(HOOK, body, content_type="application/json", HTTP_PAYMONGO_SIGNATURE=header).status_code == 200
    assert status(order) == "paid"


# Webhook: what it does


@pytest.mark.parametrize("body", ["", "[]", "1", "{}", '{"data": null}', "\x00", '{"data": {"attributes": {"type": "checkout_session.payment.paid"}}}'])
def test_malformed_event(api, pay_api, body):
    assert pay_api.send(api, body).status_code == 400
    assert pay_api.calls == []


def test_other_event_ignored(api, order, pay_api):
    pay_api.pay(order)
    r = pay_api.hook(api, order.payment_session_id, type="payment.paid")
    assert r.status_code == 200 and r.json() == {"status": "ignored"}
    assert status(order) == "pending_payment"


def test_paid_confirms_bookings(api, order_factory, pay_api):
    o = order_factory("wifi")
    pay_api.checkout(o)
    pay_api.pay(o)
    assert pay_api.hook(api, o.payment_session_id).status_code == 200
    assert status(o) == "paid" and o.paid_at
    assert o.lines.get().booking.booking_status == "confirmed"


@pytest.mark.parametrize("payment_status", [None, "pending", "failed"])
def test_paymongo_is_believed_over_the_body(api, order, pay_api, payment_status):
    if payment_status:
        pay_api.pay(order, status=payment_status)
    before = saved(order)
    assert pay_api.hook(api, order.payment_session_id).status_code == 503  # the body says paid
    assert saved(order) == before and before["order_status"] == "pending_payment"


def test_failed_attempt_before_the_paid_one_is_not_counted(api, order, pay_api):
    pay_api.pay(order, status="failed")
    pay_api.pay(order)
    pay_api.hook(api, order.payment_session_id)
    assert status(order) == "paid"


@pytest.mark.parametrize("how", ["down", "error"])
def test_paymongo_unreachable_is_503(api, order, pay_api, how):
    pay_api.pay(order)
    pay_api.down, pay_api.fail = how == "down", {"cs_1": 500}
    before = saved(order)
    assert pay_api.hook(api, order.payment_session_id).status_code == 503
    assert saved(order) == before
    pay_api.down, pay_api.fail = False, {}
    assert pay_api.hook(api, order.payment_session_id).status_code == 200  # the retry
    assert status(order) == "paid"


@pytest.mark.parametrize("reference", ["other-order", "", "00000000-0000-0000-0000-000000000000", None])
def test_session_of_another_reference_is_404(api, order, pay_api, reference):
    pay_api.pay(order)
    pay_api.sessions["cs_1"]["attributes"]["reference_number"] = reference
    before = saved(order)
    assert pay_api.hook(api, "cs_1").status_code == 404
    assert saved(order) == before


def test_session_that_is_not_the_orders_is_404(api, order, pay_api):
    pay_api.pay(order)
    Order.objects.update(payment_session_id="cs_newer")
    before = saved(order)
    assert pay_api.hook(api, "cs_1").status_code == 404
    assert saved(order) == before


@pytest.mark.parametrize("centavos", [79899, 79901, 1, 799])
def test_wrong_amount_needs_attention(api, order, pay_api, centavos):
    pay_api.pay(order, centavos)
    assert pay_api.hook(api, order.payment_session_id).status_code == 200
    assert status(order) == "pending_payment" and order.needs_attention
    assert "cs_1" in order.attention_note and f"{centavos // 100}.{centavos % 100:02d}" in order.attention_note and "799.00" in order.attention_note
    before = saved(order)
    pay_api.hook(api, order.payment_session_id)
    assert saved(order) == before


def test_duplicate_is_noop(api, order, pay_api):
    pay_api.pay(order)
    pay_api.hook(api, order.payment_session_id)
    before = saved(order)
    assert pay_api.hook(api, order.payment_session_id).status_code == 200
    assert saved(order) == before


def test_second_payment_of_a_paid_order_needs_attention(api, order, pay_api):
    pay_api.pay(order)
    pay_api.hook(api, order.payment_session_id)
    pay_api.pay(order)
    pay_api.hook(api, order.payment_session_id)
    assert status(order) == "paid" and order.needs_attention and "1598.00" in order.attention_note


def test_stale_lower_amount_changes_nothing(api, order, pay_api):
    from payments.paymongo import get_session
    from payments.settle import settle

    pay_api.pay(order)
    stale = get_session(order.payment_session_id)  # fetched before the second payment, settled after it
    pay_api.pay(order)
    pay_api.hook(api, order.payment_session_id)
    before = saved(order)
    settle(stale)
    assert saved(order) == before


@pytest.mark.parametrize("closed", ["cancelled", "expired", "refunded", "fulfilled"])
def test_payment_of_a_closed_order_needs_attention_once(api, order, pay_api, closed):
    Order.objects.update(order_status=closed, attention_note="Earlier note")
    pay_api.pay(order)
    assert pay_api.hook(api, order.payment_session_id).status_code == 200
    assert status(order) == closed and order.needs_attention and not order.paid_at
    assert order.attention_note.startswith("Earlier note\n") and "cs_1" in order.attention_note
    before = saved(order)
    pay_api.hook(api, order.payment_session_id)
    assert saved(order) == before


@pytest.mark.parametrize("later", ["fulfilled", "refunded", "cancelled"])
def test_repeat_after_a_paid_order_moved_on_is_noop(api, admin_api, order, pay_api, later):
    pay_api.pay(order)
    pay_api.hook(api, order.payment_session_id)
    admin_api.patch(f"/api/v1/staff/orders/{order.id}", {"order_status": later}, format="json")
    before = saved(order)
    assert before["order_status"] == later
    pay_api.hook(api, order.payment_session_id)
    assert saved(order) == before  # the same payment must not look like a second one


def test_payment_of_an_order_marked_paid_by_staff_is_flagged_once(api, admin_api, order, pay_api):
    admin_api.patch(f"/api/v1/staff/orders/{order.id}", {"order_status": "paid"}, format="json")
    order.refresh_from_db()
    first_paid_at = order.paid_at
    pay_api.pay(order)
    pay_api.hook(api, order.payment_session_id)
    assert status(order) == "paid" and order.paid_at == first_paid_at
    assert order.needs_attention and "after the order was paid" in order.attention_note
    before = saved(order)
    pay_api.hook(api, order.payment_session_id)
    assert saved(order) == before


@pytest.mark.parametrize("was,now", [("pending_payment", "paid"), ("cancelled", "cancelled")])
def test_payment_of_a_deleted_order_restores_and_flags_it(api, order, pay_api, was, now):
    Order.objects.update(order_status=was)
    order.soft_delete()
    pay_api.pay(order)
    assert pay_api.hook(api, order.payment_session_id).status_code == 200
    assert status(order) == now and order.deleted_at is None
    assert order.needs_attention and "deleted order was paid" in order.attention_note and "cs_1" in order.attention_note
    order.soft_delete()
    before = saved(order)
    pay_api.hook(api, order.payment_session_id)
    assert saved(order) == before  # staff may delete it again once handled


def test_wrong_amount_for_a_deleted_order_has_both_notes(api, order, pay_api):
    order.soft_delete()
    pay_api.pay(order, 100)
    pay_api.hook(api, order.payment_session_id)
    assert status(order) == "pending_payment" and order.deleted_at is None
    assert "deleted order was paid" in order.attention_note and "PHP 1.00" in order.attention_note


def test_attention_note_tells_staff_what_to_do(api, order, pay_api):
    Order.objects.update(order_status="cancelled")
    pay_api.pay(order)
    pay_api.hook(api, order.payment_session_id)
    order.refresh_from_db()
    assert order.attention_note.endswith("refund the traveler there or handle the order manually.")


# expire_unpaid_orders


def age(order, **delta):
    Order.all_objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(**delta))


def test_expire_unpaid_order_cancels_its_booking(order_factory, pay_api):
    o = order_factory("wifi")
    pay_api.checkout(o)
    age(o, hours=24, minutes=1)
    call_command("expire_unpaid_orders")
    assert status(o) == "expired" and o.lines.get().booking.booking_status == "cancelled"
    assert pay_api.sessions["cs_1"]["attributes"]["status"] == "expired"


def test_expire_settles_an_order_paid_meanwhile(order_factory, pay_api):
    o = order_factory("wifi")
    pay_api.checkout(o)
    pay_api.pay(o)
    age(o, hours=25)
    call_command("expire_unpaid_orders")
    assert status(o) == "paid" and o.paid_at and o.lines.get().booking.booking_status == "confirmed"


def test_expire_flags_a_wrong_amount(order, pay_api):
    pay_api.pay(order, 100)
    age(order, hours=25)
    call_command("expire_unpaid_orders")
    assert status(order) == "pending_payment" and order.needs_attention


def test_one_failing_order_does_not_stop_the_others(order_factory, pay_api):
    orders = [order_factory() for _ in range(3)]
    for o in orders:
        pay_api.checkout(o)
        age(o, hours=25)
    pay_api.fail = {orders[1].payment_session_id: 500}
    call_command("expire_unpaid_orders")
    assert [status(o) for o in orders] == ["expired", "pending_payment", "expired"]
    pay_api.fail = {}
    call_command("expire_unpaid_orders")
    assert status(orders[1]) == "expired"


def test_expire_leaves_everything_when_paymongo_is_down(order, pay_api):
    age(order, hours=25)
    pay_api.down = True
    call_command("expire_unpaid_orders")
    assert status(order) == "pending_payment"


def test_expire_handles_an_already_expired_session(order, pay_api):
    paymongo.expire_checkout(order)  # an earlier run stopped right after this
    age(order, hours=25)
    call_command("expire_unpaid_orders")
    assert status(order) == "expired"


def test_order_stays_open_while_its_session_could_not_be_closed(order, pay_api, monkeypatch):
    def refuse(order):
        raise requests.HTTPError("400")

    monkeypatch.setattr(paymongo, "expire_checkout", refuse)
    age(order, hours=25)
    call_command("expire_unpaid_orders")
    assert status(order) == "pending_payment"


def test_paid_session_whose_expire_is_refused_is_settled(order, pay_api):
    pay_api.pay(order)
    pay_api.sessions["cs_1"]["attributes"]["status"] = "other"  # the fake refuses to expire it
    age(order, hours=25)
    call_command("expire_unpaid_orders")
    assert status(order) == "paid"


def test_expire_keeps_a_status_changed_meanwhile(api, order, pay_api, monkeypatch):
    def pay_after_fetch(session_id):
        session = real(session_id)
        pay_api.pay(order)
        monkeypatch.setattr(paymongo, "get_session", real)
        pay_api.hook(api, session_id)
        return session  # fetched before the payment

    real = paymongo.get_session
    monkeypatch.setattr(paymongo, "get_session", pay_after_fetch)
    age(order, hours=25)
    call_command("expire_unpaid_orders")
    assert status(order) == "paid"


def test_younger_order_untouched_and_hours_option(order, pay_api):
    age(order, hours=23, minutes=59)
    calls = len(pay_api.calls)
    call_command("expire_unpaid_orders")
    assert status(order) == "pending_payment" and len(pay_api.calls) == calls
    call_command("expire_unpaid_orders", hours=23)
    assert status(order) == "expired"


def test_order_without_session_is_expired_directly(order_factory, pay_api):
    o = order_factory()
    age(o, hours=25)
    call_command("expire_unpaid_orders")
    assert status(o) == "expired" and pay_api.calls == []


@pytest.mark.parametrize("state", ["paid", "cancelled", "fulfilled", "refunded"])
def test_expire_ignores_orders_not_pending(order, pay_api, state):
    Order.objects.update(order_status=state)
    age(order, hours=25)
    calls = len(pay_api.calls)
    call_command("expire_unpaid_orders")
    assert status(order) == state and len(pay_api.calls) == calls


def test_payment_after_expiry_is_flagged(api, order, pay_api):
    age(order, hours=25)
    call_command("expire_unpaid_orders")
    pay_api.pay(order)
    assert pay_api.hook(api, order.payment_session_id).status_code == 200
    assert status(order) == "expired" and order.needs_attention
