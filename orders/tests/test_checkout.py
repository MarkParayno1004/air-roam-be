from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from bookings.models import Booking
from orders.models import Order

pytestmark = pytest.mark.django_db
URL = "/api/v1/orders"


def day(n):
    """Local midnight n days from today, ISO."""
    d = timezone.localtime() + timedelta(days=n)
    return d.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


@pytest.fixture(autouse=True)
def fake_invoice(monkeypatch):
    from payments import xendit

    def create_invoice(order):
        order.xendit_invoice_id, order.xendit_invoice_url = "inv_1", "https://checkout.xendit.co/inv_1"
        order.save(update_fields=["xendit_invoice_id", "xendit_invoice_url"])
        return order.xendit_invoice_id, order.xendit_invoice_url

    monkeypatch.setattr(xendit, "create_invoice", create_invoice)


@pytest.fixture
def wifi(variant_factory):
    return variant_factory(product_type="pocket_wifi", name="Japan Pocket WiFi", price=Decimal("350.00"), pricing_unit="per_day", validity_days=None)


def line(v, **kw):
    return {"variant_id": str(v.id), "quantity": 1, "expected_unit_price": str(v.price), **kw}


def post(client, *lines):
    return client.post(URL, {"client": "web", "lines": list(lines)}, format="json")


def test_checkout_requires_login(api, variant_factory):
    assert post(api, line(variant_factory())).status_code == 401


def test_checkout_per_plan_total(auth_api, variant_factory):
    v = variant_factory()
    r = post(auth_api, line(v, quantity=2))
    assert r.status_code == 201, r.content
    body = r.json()
    assert body["invoice_url"] == "https://checkout.xendit.co/inv_1"
    assert body["order"]["total_amount"] == "1598.00" and body["order"]["order_status"] == "pending_payment"
    assert body["price_updates"] == [] and body["removed_lines"] == []
    assert body["order"]["lines"][0]["booking"] is None
    assert body["order"]["lines"][0]["countries_snapshot"] == ["JP"]


def test_checkout_pocket_wifi_rental(auth_api, wifi):
    r = post(auth_api, line(wifi, start_at=day(19), end_at=day(25)))
    assert r.status_code == 201, r.content
    ln = r.json()["order"]["lines"][0]
    assert ln["rental_days"] == 6 and ln["line_total"] == "2100.00"
    assert ln["booking"]["booking_status"] == "pending" and ln["booking"]["destination_country_codes"] == ["JP"]


def test_checkout_syncs_changed_price(auth_api, variant_factory):
    v = variant_factory()
    r = post(auth_api, line(v, expected_unit_price="749.00"))
    assert r.status_code == 201
    assert r.json()["price_updates"] == [{"variant_id": str(v.id), "name": v.name, "old_unit_price": "749.00", "new_unit_price": "799.00"}]
    assert r.json()["order"]["total_amount"] == "799.00"


def test_checkout_removes_unavailable_line(auth_api, variant_factory):
    keep, gone = variant_factory(), variant_factory(name="Old plan", is_active=False)
    r = post(auth_api, line(keep), line(gone))
    assert r.status_code == 201
    assert r.json()["removed_lines"] == [{"variant_id": str(gone.id), "name": "Old plan"}]
    assert len(r.json()["order"]["lines"]) == 1


def test_checkout_unknown_variant_removed(auth_api, variant_factory):
    keep = variant_factory()
    r = post(auth_api, line(keep), {"variant_id": "00000000-0000-0000-0000-000000000000", "quantity": 1, "expected_unit_price": "1.00"})
    assert r.status_code == 201 and r.json()["removed_lines"][0]["name"] == ""


def test_checkout_nothing_to_buy(auth_api, variant_factory):
    r = post(auth_api, line(variant_factory(is_active=False)))
    assert r.status_code == 409 and r.json()["code"] == "nothing_to_buy"
    assert Order.all_objects.count() == 0


@pytest.mark.parametrize(
    "extra",
    [{"quantity": 0}, {"quantity": -1}, {"quantity": 11}],
)
def test_checkout_rejects_bad_quantity(auth_api, variant_factory, extra):
    assert post(auth_api, line(variant_factory(), **extra)).status_code == 400
    assert Order.all_objects.count() == 0


def test_checkout_rejects_bad_rental_lines(auth_api, wifi):
    bad = [
        {},  # missing dates
        {"start_at": day(5), "end_at": day(5)},
        {"start_at": day(5), "end_at": day(3)},
        {"start_at": day(-2), "end_at": day(3)},
        {"start_at": day(5), "end_at": day(8), "destination_country_codes": ["KR"]},
    ]
    for extra in bad:
        assert post(auth_api, line(wifi, **extra)).status_code == 400, extra
    assert Order.all_objects.count() == 0


def test_checkout_rejects_empty_lines(auth_api):
    assert auth_api.post(URL, {"client": "web", "lines": []}, format="json").status_code == 400


def test_pack_destinations_subset(auth_api, variant_factory):
    pack = variant_factory(product_type="pocket_wifi", name="Asia WiFi", countries=["JP", "KR", "SG"], price=Decimal("450.00"), pricing_unit="per_day")
    r = post(auth_api, line(pack, start_at=day(3), end_at=day(5), destination_country_codes=["kr"]))
    assert r.status_code == 201, r.content
    assert Booking.objects.get().destination_country_codes == ["KR"]


def test_xendit_failure_cancels_order(auth_api, variant_factory, monkeypatch):
    from payments import xendit

    def boom(order):
        raise RuntimeError("xendit down")

    monkeypatch.setattr(xendit, "create_invoice", boom)
    r = post(auth_api, line(variant_factory()))
    assert r.status_code == 502 and r.json()["code"] == "payment_provider_unavailable"
    assert Order.objects.get().order_status == "cancelled"


def test_orders_list_and_detail_are_private(auth_api, other_api, variant_factory):
    oid = post(auth_api, line(variant_factory())).json()["order"]["id"]
    assert [o["id"] for o in auth_api.get(URL).json()["results"]] == [oid]
    assert other_api.get(f"{URL}/{oid}").status_code == 404
    assert other_api.get(URL).json()["results"] == []


def test_cancel_only_pending(auth_api, variant_factory):
    oid = post(auth_api, line(variant_factory())).json()["order"]["id"]
    r = auth_api.post(f"{URL}/{oid}/cancel")
    assert r.status_code == 200 and r.json()["order_status"] == "cancelled"
    assert auth_api.post(f"{URL}/{oid}/cancel").json()["code"] == "invalid_transition"
