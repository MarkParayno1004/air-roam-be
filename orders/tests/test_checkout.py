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
    """Asia 1 (JP, KR) 100/day with a 399 plan, NA (US) 50/day, EU (FR) 10/day (unlimited WiFi); an eSIM and a Pocket WiFi product."""

    def __init__(self, region_factory, plan_factory, wifi_plan_factory, product_factory):
        self.asia = region_factory(name="Asia 1", countries=["JP", "KR"])
        self.na = region_factory(name="NA", countries=["US"])
        self.eu = region_factory(name="EU", countries=["FR"])
        asia_wifi = wifi_plan_factory(region=self.asia)
        self.wifi_plans = {"JP": asia_wifi, "KR": asia_wifi, "US": wifi_plan_factory(region=self.na, price=Decimal("50.00")), "FR": wifi_plan_factory(region=self.eu, price=Decimal("10.00"))}
        self.plan = plan_factory(region=self.asia)
        self.esim_product = product_factory("esim")
        self.wifi_product = product_factory("pocket_wifi")

    def esim(self, code="JP", expected="399.00", **kw):
        return {"product_id": str(self.esim_product.id), "country_code": code, "region_plan_id": str(self.plan.id), "quantity": 1, "expected_unit_price": expected, **kw}

    def wifi(self, code="JP", days=2, expected="100.00", **kw):
        plan = self.wifi_plans[code.upper()]
        return {"product_id": str(self.wifi_product.id), "country_code": code, "region_plan_id": str(plan.id), "quantity": 1, "expected_unit_price": expected, "start_at": day(5), "end_at": day(5 + days), **kw}


@pytest.fixture
def world(region_factory, plan_factory, wifi_plan_factory, product_factory):
    return World(region_factory, plan_factory, wifi_plan_factory, product_factory)


def post(client, *lines):
    return client.post(URL, {"client": "web", "lines": list(lines)}, format="json")


def ok(client, *lines):
    r = post(client, *lines)
    assert r.status_code == 201, r.content
    return r.json()


def test_checkout_requires_login(api, world):
    assert post(api, world.esim()).status_code == 401


@pytest.mark.parametrize("trips,fee,total", [
    ([("JP", 2), ("US", 2), ("FR", 2)], "200.00", "520.00"),
    ([("JP", 2), ("US", 2), ("FR", 3)], "200.00", "530.00"),  # exactly 7 days still pays
    ([("JP", 2), ("US", 2), ("FR", 4)], "0.00", "340.00"),
    ([("FR", 30), ("JP", 2)], "0.00", "500.00"),
    ([("US", 2), ("FR", 2)], "200.00", "320.00"),
])
def test_own_rates_and_delivery_fee(auth_api, world, trips, fee, total):
    rates = {"JP": "100.00", "US": "50.00", "FR": "10.00"}
    body = ok(auth_api, *[world.wifi(code, days, expected=rates[code]) for code, days in trips])
    order = body["order"]
    assert {l["countries_snapshot"][0]: l["unit_price"] for l in order["lines"]} == {code: rates[code] for code, _ in trips}
    assert order["delivery_fee"] == fee and order["total_amount"] == total
    assert body["price_updates"] == [] and body["removed_lines"] == []


def test_quantity_does_not_multiply_days(auth_api, world):
    order = ok(auth_api, world.wifi(days=4, quantity=2))["order"]  # 4 days, not 8
    assert (order["delivery_fee"], order["total_amount"]) == ("200.00", "1000.00")


def test_wifi_creates_a_pending_booking(auth_api, world):
    ln = ok(auth_api, world.wifi("jp", days=6))["order"]["lines"][0]
    assert ln["rental_days"] == 6 and ln["line_total"] == "600.00" and ln["region_plan"] == str(world.wifi_plans["JP"].id)
    assert ln["variant_name_snapshot"] == "Japan Unlimited" and ln["product_name_snapshot"] == "Air Roam pocket_wifi" and ln["pricing_unit_snapshot"] == "per_day"
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


def test_removed_line_does_not_count_its_days(auth_api, world):
    world.asia.is_active = False
    world.asia.save()
    body = ok(auth_api, world.wifi("JP", 10), world.wifi("US", 2, expected="50.00"))
    assert body["removed_lines"] == [{"name": "Air Roam pocket_wifi · Japan Unlimited"}]
    assert body["price_updates"] == []
    assert (body["order"]["delivery_fee"], body["order"]["total_amount"]) == ("200.00", "300.00")


@pytest.mark.parametrize("how", ["inactive", "deleted"])
def test_unavailable_wifi_plan_removed(auth_api, world, how):
    plan = world.wifi_plans["US"]
    if how == "deleted":
        plan.soft_delete()
    else:
        plan.is_active = False
        plan.save()
    assert ok(auth_api, world.wifi("JP"), world.wifi("US"))["removed_lines"] == [{"name": "Air Roam pocket_wifi · United States of America Unlimited"}]


def test_wifi_lines_pay_their_own_plan_price(auth_api, world, wifi_plan_factory):
    regular = wifi_plan_factory(region=world.asia, name="Regular", data_mb=1024, price=Decimal("200.00"))
    world.wifi_plans["US"].price = Decimal("500.00")
    world.wifi_plans["US"].save()
    body = ok(auth_api, world.wifi("JP", expected="200.00", region_plan_id=str(regular.id)), world.wifi("US", expected="500.00"))
    lines = {l["variant_name_snapshot"]: l for l in body["order"]["lines"]}
    assert {n: l["unit_price"] for n, l in lines.items()} == {"Japan Regular · 1GB/day": "200.00", "United States of America Unlimited": "500.00"}
    assert lines["Japan Regular · 1GB/day"]["region_plan"] == str(regular.id)
    assert body["price_updates"] == [] and body["order"]["total_amount"] == "1600.00"  # 2 x 200 + 2 x 500 + 200 delivery


def test_wifi_and_sim_plans_cannot_be_swapped(auth_api, world):
    swapped = [world.wifi(region_plan_id=str(world.plan.id)), world.esim(region_plan_id=str(world.wifi_plans["JP"].id))]
    for line in swapped:
        r = post(auth_api, line)
        assert r.status_code == 409 and r.json()["code"] == "nothing_to_buy"
    body = ok(auth_api, world.esim(), *swapped)
    assert len(body["removed_lines"]) == 2 and len(body["order"]["lines"]) == 1


def test_wifi_plan_from_region_not_covering_country_removed(auth_api, world):
    r = post(auth_api, world.wifi("US", region_plan_id=str(world.wifi_plans["FR"].id)))
    assert r.status_code == 409 and r.json()["code"] == "nothing_to_buy"


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
    assert body["removed_lines"] == [{"name": "Air Roam esim · Japan 5GB · 7 days"}] and len(body["order"]["lines"]) == 1


def test_unknown_product_plan_or_country_removed(auth_api, world):
    body = ok(auth_api, world.esim(), world.esim(product_id=NOWHERE), world.esim(region_plan_id=NOWHERE), world.wifi(country_code="ZZ"))
    assert body["removed_lines"] == [{"name": ""}] * 3 and len(body["order"]["lines"]) == 1


@pytest.mark.parametrize("kind", ["esim", "wifi"])
def test_line_without_plan_rejected(auth_api, world, kind):
    for extra in ({"region_plan_id": None}, {}):
        line = getattr(world, kind)(**extra)
        if not extra:
            del line["region_plan_id"]
        r = post(auth_api, line)
        assert r.status_code == 400 and r.json()["code"] == "plan_required"
    assert Order.all_objects.count() == 0


def test_changed_plan_price_is_reported(auth_api, world):
    body = ok(auth_api, world.esim(expected="349.00"))
    assert body["price_updates"] == [{"name": "Air Roam esim · Japan 5GB · 7 days", "old_unit_price": "349.00", "new_unit_price": "399.00"}]
    assert body["order"]["total_amount"] == "399.00"


def test_later_region_edit_keeps_order(auth_api, world):
    before = ok(auth_api, world.esim(), world.wifi())["order"]
    world.asia.countries = ["SG"]
    world.asia.save()
    wifi = world.wifi_plans["JP"]
    wifi.price, wifi.name = Decimal("999.00"), "Renamed"
    wifi.save()
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


def whole_region(world):
    world.asia.name = "Asia"
    world.asia.save()
    return {k: v for k, v in world.esim().items() if k != "country_code"}


def test_plan_without_country_covers_the_whole_region(auth_api, world):
    ln = ok(auth_api, whole_region(world))["order"]["lines"][0]
    assert ln["variant_name_snapshot"] == "Asia 5GB · 7 days" and ln["countries_snapshot"] == ["JP", "KR"]
    assert ln["unit_price"] == "399.00" and ln["booking"] is None


def test_wifi_without_country_is_rejected(auth_api, world):
    line = {k: v for k, v in world.wifi().items() if k != "country_code"}
    r = post(auth_api, line)
    assert r.status_code == 400 and r.json()["code"] == "country_required"


def test_whole_region_line_removed_when_region_inactive(auth_api, world):
    line = whole_region(world)
    world.asia.is_active = False
    world.asia.save()
    body = ok(auth_api, line, world.wifi("US", expected="50.00"))
    assert body["removed_lines"] == [{"name": "Air Roam esim · Asia 5GB · 7 days"}] and len(body["order"]["lines"]) == 1
