from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from bookings.models import Booking
from orders.models import Order

pytestmark = pytest.mark.django_db
URL = "/api/v1/orders"
NOWHERE = "00000000-0000-0000-0000-000000000000"


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


class World:
    """Asia 1 (JP, KR) 100/day with a 399 plan, NA (US) 50/day, EU (FR) 10/day; an eSIM and a Pocket WiFi product."""

    def __init__(self, region_factory, plan_factory, product_factory):
        self.asia = region_factory(name="Asia 1", countries=["JP", "KR"], pocket_wifi_daily_rate=Decimal("100.00"))
        self.na = region_factory(name="NA", countries=["US"], pocket_wifi_daily_rate=Decimal("50.00"))
        self.eu = region_factory(name="EU", countries=["FR"], pocket_wifi_daily_rate=Decimal("10.00"))
        self.plan = plan_factory(region=self.asia)
        self.esim_product = product_factory("esim")
        self.wifi_product = product_factory("pocket_wifi")

    def esim(self, code="JP", expected="399.00", **kw):
        return {"product_id": str(self.esim_product.id), "country_code": code, "region_plan_id": str(self.plan.id), "quantity": 1, "expected_unit_price": expected, **kw}

    def wifi(self, code="JP", days=2, expected="100.00", **kw):
        return {"product_id": str(self.wifi_product.id), "country_code": code, "quantity": 1, "expected_unit_price": expected, "start_at": day(5), "end_at": day(5 + days), **kw}


@pytest.fixture
def world(region_factory, plan_factory, product_factory):
    return World(region_factory, plan_factory, product_factory)


def post(client, *lines):
    return client.post(URL, {"client": "web", "lines": list(lines)}, format="json")


def ok(client, *lines):
    r = post(client, *lines)
    assert r.status_code == 201, r.content
    return r.json()


def test_checkout_requires_login(api, world):
    assert post(api, world.esim()).status_code == 401


@pytest.mark.parametrize("trips,rate,fee,total", [
    ([("JP", 2), ("US", 2), ("FR", 2)], "100.00", "200.00", "800.00"),
    ([("JP", 2), ("US", 2), ("FR", 3)], "100.00", "200.00", "900.00"),  # exactly 7 days still pays
    ([("JP", 2), ("US", 2), ("FR", 4)], "100.00", "0.00", "800.00"),
    ([("FR", 30), ("JP", 2)], "100.00", "0.00", "3200.00"),
    ([("US", 2), ("FR", 2)], "50.00", "200.00", "400.00"),
])
def test_highest_rate_and_delivery_fee(auth_api, world, trips, rate, fee, total):
    body = ok(auth_api, *[world.wifi(code, days, expected=rate) for code, days in trips])
    order = body["order"]
    assert [l["unit_price"] for l in order["lines"]] == [rate] * len(trips)
    assert order["delivery_fee"] == fee and order["total_amount"] == total
    assert body["price_updates"] == [] and body["removed_lines"] == []


def test_quantity_does_not_multiply_days(auth_api, world):
    order = ok(auth_api, world.wifi(days=4, quantity=2))["order"]  # 4 days, not 8
    assert (order["delivery_fee"], order["total_amount"]) == ("200.00", "1000.00")


def test_wifi_creates_a_pending_booking(auth_api, world):
    ln = ok(auth_api, world.wifi("jp", days=6))["order"]["lines"][0]
    assert ln["rental_days"] == 6 and ln["line_total"] == "600.00" and ln["region_plan"] is None
    assert ln["variant_name_snapshot"] == "Japan Pocket WiFi" and ln["pricing_unit_snapshot"] == "per_day"
    assert ln["booking"]["booking_status"] == "pending" and ln["booking"]["destination_country_codes"] == ["JP"]


def test_esim_only_has_no_fee(auth_api, world):
    body = ok(auth_api, world.esim(quantity=2))
    assert body["invoice_url"] == "https://checkout.xendit.co/inv_1"
    order = body["order"]
    assert (order["delivery_fee"], order["total_amount"], order["order_status"]) == ("0.00", "798.00", "pending_payment")
    ln = order["lines"][0]
    assert ln["booking"] is None and ln["variant_name_snapshot"] == "Japan 5GB · 7 days" and ln["countries_snapshot"] == ["JP"]


def test_esim_plus_wifi(auth_api, world):
    order = ok(auth_api, world.esim(), world.wifi())["order"]
    assert order["total_amount"] == "799.00"
    assert {l["unit_price"] for l in order["lines"]} == {"399.00", "100.00"}


def test_removed_line_does_not_set_the_rate_or_days(auth_api, world):
    world.asia.is_active = False
    world.asia.save()
    body = ok(auth_api, world.wifi("JP", 10), world.wifi("US", 2))
    assert body["removed_lines"] == [{"name": "Japan Pocket WiFi"}]
    assert body["price_updates"] == [{"name": "United States of America Pocket WiFi", "old_unit_price": "100.00", "new_unit_price": "50.00"}]
    assert (body["order"]["delivery_fee"], body["order"]["total_amount"]) == ("200.00", "300.00")


def test_country_without_wifi_rate_removed(auth_api, world):
    world.na.pocket_wifi_daily_rate = None
    world.na.save()
    assert ok(auth_api, world.wifi("JP"), world.wifi("US"))["removed_lines"][0]["name"].endswith("Pocket WiFi")


def test_plan_from_region_not_covering_country_removed(auth_api, world):
    r = post(auth_api, world.esim("FR"))
    assert r.status_code == 409 and r.json()["code"] == "nothing_to_buy"
    assert Order.all_objects.count() == 0


@pytest.mark.parametrize("target", ["plan", "asia", "esim_product"])
@pytest.mark.parametrize("how", ["inactive", "deleted"])
def test_unavailable_plan_region_or_product_removed(auth_api, world, target, how):
    obj = getattr(world, target)
    if how == "deleted":
        obj.soft_delete()
    else:
        obj.is_active = False
        obj.save()
    body = ok(auth_api, world.esim(), world.wifi("US", expected="50.00"))
    assert body["removed_lines"] == [{"name": "Japan 5GB · 7 days"}] and len(body["order"]["lines"]) == 1


def test_unknown_product_plan_or_country_removed(auth_api, world):
    body = ok(auth_api, world.esim(), world.esim(product_id=NOWHERE), world.esim(region_plan_id=NOWHERE), world.wifi("ZZ"))
    assert body["removed_lines"] == [{"name": ""}] * 3 and len(body["order"]["lines"]) == 1


def test_esim_without_plan_rejected(auth_api, world):
    for extra in ({"region_plan_id": None}, {}):
        line = world.esim(**extra)
        if not extra:
            del line["region_plan_id"]
        r = post(auth_api, line)
        assert r.status_code == 400 and r.json()["code"] == "plan_required"
    assert Order.all_objects.count() == 0


def test_wifi_ignores_a_plan_id(auth_api, world):
    ln = ok(auth_api, world.wifi(region_plan_id=str(world.plan.id)))["order"]["lines"][0]
    assert ln["region_plan"] is None and ln["unit_price"] == "100.00"


def test_changed_plan_price_is_reported(auth_api, world):
    body = ok(auth_api, world.esim(expected="349.00"))
    assert body["price_updates"] == [{"name": "Japan 5GB · 7 days", "old_unit_price": "349.00", "new_unit_price": "399.00"}]
    assert body["order"]["total_amount"] == "399.00"


def test_later_region_edit_keeps_order(auth_api, world):
    before = ok(auth_api, world.esim(), world.wifi())["order"]
    world.asia.pocket_wifi_daily_rate, world.asia.countries = Decimal("999.00"), ["SG"]
    world.asia.save()
    world.plan.price, world.plan.data_mb = Decimal("1.00"), None
    world.plan.save()
    assert auth_api.get(f"{URL}/{before['id']}").json() == before


@pytest.mark.parametrize("extra", [{"quantity": 0}, {"quantity": -1}, {"quantity": 11}])
def test_checkout_rejects_bad_quantity(auth_api, world, extra):
    assert post(auth_api, world.esim(**extra)).status_code == 400
    assert Order.all_objects.count() == 0


def test_checkout_rejects_bad_rental_dates(auth_api, world):
    bad = [{"start_at": day(5), "end_at": day(5)}, {"start_at": day(5), "end_at": day(3)}, {"start_at": day(-2), "end_at": day(3)}]
    for extra in bad:
        assert post(auth_api, world.wifi(**extra)).status_code == 400, extra
    missing = world.wifi()
    del missing["start_at"], missing["end_at"]
    assert post(auth_api, missing).status_code == 400
    assert Order.all_objects.count() == 0 and Booking.objects.count() == 0


def test_checkout_rejects_empty_lines(auth_api):
    assert auth_api.post(URL, {"client": "web", "lines": []}, format="json").status_code == 400


def test_xendit_failure_cancels_order(auth_api, world, monkeypatch):
    from payments import xendit

    def boom(order):
        raise RuntimeError("xendit down")

    monkeypatch.setattr(xendit, "create_invoice", boom)
    r = post(auth_api, world.esim())
    assert r.status_code == 502 and r.json()["code"] == "payment_provider_unavailable"
    assert Order.objects.get().order_status == "cancelled"


def test_orders_list_and_detail_are_private(auth_api, other_api, world):
    oid = ok(auth_api, world.esim())["order"]["id"]
    assert [o["id"] for o in auth_api.get(URL).json()["results"]] == [oid]
    assert other_api.get(f"{URL}/{oid}").status_code == 404
    assert other_api.get(URL).json()["results"] == []


def test_cancel_only_pending(auth_api, world):
    oid = ok(auth_api, world.esim())["order"]["id"]
    r = auth_api.post(f"{URL}/{oid}/cancel")
    assert r.status_code == 200 and r.json()["order_status"] == "cancelled"
    assert auth_api.post(f"{URL}/{oid}/cancel").json()["code"] == "invalid_transition"
