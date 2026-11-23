import pytest

from payments import xendit

pytestmark = pytest.mark.django_db
HOOK = "/api/v1/payments/xendit/webhook"
TOKEN = "test-callback-token"


@pytest.fixture(autouse=True)
def xendit_settings(settings):
    settings.XENDIT_SECRET_KEY = "xnd_development_abc"
    settings.XENDIT_CALLBACK_TOKEN = TOKEN
    settings.WEB_STORE_URL = "https://airroam.test"
    settings.APP_DEEP_LINK = "airroam://payment-result"


class FakeResp:
    def __init__(self, status=200, data=None):
        self.status_code, self._data = status, data or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_create_invoice_payload_and_redirect(monkeypatch, order_factory):
    sent = {}

    def fake_post(url, json, auth, timeout):
        sent.update(url=url, json=json, auth=auth, timeout=timeout)
        return FakeResp(200, {"id": "inv_9", "invoice_url": "https://checkout.xendit.co/inv_9"})

    monkeypatch.setattr(xendit.requests, "post", fake_post)
    order = order_factory()
    assert xendit.create_invoice(order) == ("inv_9", "https://checkout.xendit.co/inv_9")
    order.refresh_from_db()
    assert order.xendit_invoice_id == "inv_9" and order.xendit_invoice_url.endswith("inv_9")
    assert sent["url"] == "https://api.xendit.co/v2/invoices" and sent["auth"] == ("xnd_development_abc", "") and sent["timeout"] == 10
    body = sent["json"]
    assert body["external_id"] == str(order.id) and body["currency"] == "PHP" and body["amount"] == 799.0
    assert body["success_redirect_url"] == f"https://airroam.test/payment-result?order_id={order.id}"
    assert body["failure_redirect_url"] == body["success_redirect_url"]


def test_create_invoice_app_deep_link(monkeypatch, order_factory):
    sent = {}
    monkeypatch.setattr(xendit.requests, "post", lambda url, json, auth, timeout: sent.update(json) or FakeResp(200, {"id": "i", "invoice_url": "u"}))
    order = order_factory(client="app")
    xendit.create_invoice(order)
    assert sent["success_redirect_url"] == f"airroam://payment-result?order_id={order.id}"


def test_create_invoice_raises_on_error(monkeypatch, order_factory):
    monkeypatch.setattr(xendit.requests, "post", lambda *a, **k: FakeResp(500))
    with pytest.raises(Exception):
        xendit.create_invoice(order_factory())


def _hook(api, order, status="PAID", amount=None, token=TOKEN):
    payload = {"id": "inv_1", "external_id": str(order.id), "status": status, "amount": float(amount if amount is not None else order.total_amount)}
    return api.post(HOOK, payload, format="json", HTTP_X_CALLBACK_TOKEN=token)


def test_webhook_rejects_bad_token(api, order_factory):
    assert _hook(api, order_factory(), token="nope").status_code == 403


def test_webhook_unknown_order_404(api, order_factory):
    o = order_factory()
    payload = {"external_id": "00000000-0000-0000-0000-000000000000", "status": "PAID", "amount": 1}
    assert api.post(HOOK, payload, format="json", HTTP_X_CALLBACK_TOKEN=TOKEN).status_code == 404
    assert o.order_status == "pending_payment"


def test_webhook_paid_confirms_bookings(api, order_factory):
    o = order_factory("wifi")
    assert _hook(api, o).status_code == 200
    o.refresh_from_db()
    assert o.order_status == "paid" and o.paid_at
    assert o.lines.get().booking.booking_status == "confirmed"


def test_webhook_amount_mismatch(api, order_factory):
    o = order_factory()
    assert _hook(api, o, amount=1).status_code == 400
    o.refresh_from_db()
    assert o.order_status == "pending_payment"


def test_duplicate_paid_webhook_is_noop(api, order_factory):
    o = order_factory()
    _hook(api, o)
    o.refresh_from_db()
    first_paid_at = o.paid_at
    assert _hook(api, o).status_code == 200
    o.refresh_from_db()
    assert o.paid_at == first_paid_at


def test_expired_webhook(api, order_factory):
    o = order_factory()
    assert _hook(api, o, status="EXPIRED").status_code == 200
    o.refresh_from_db()
    assert o.order_status == "expired"


def test_paid_after_expired_ignored(api, order_factory):
    o = order_factory()
    _hook(api, o, status="EXPIRED")
    assert _hook(api, o).status_code == 200
    o.refresh_from_db()
    assert o.order_status == "expired"
