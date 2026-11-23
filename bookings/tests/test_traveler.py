from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from bookings.models import Booking
from orders.checkout import create_order

pytestmark = pytest.mark.django_db
V1 = "/api/v1"


def iso(days):
    return (timezone.now() + timedelta(days=days)).isoformat()


def _paid(order):
    order.order_status = "paid"
    order.save()
    return order


@pytest.fixture
def paid_esim_line(order_factory):
    return _paid(order_factory()).lines.get()


@pytest.fixture
def pending_esim_line(order_factory):
    return order_factory().lines.get()


@pytest.fixture
def paid_pack_line(variant_factory, user):
    v = variant_factory(name="Asia 3", countries=["JP", "KR", "SG"], price=Decimal("999.00"))
    o = create_order(user, "web", [{"variant_id": v.id, "quantity": 1, "expected_unit_price": v.price}]).order
    return _paid(o).lines.get()


def book(client, line, **body):
    body = {"start_at": iso(3), "end_at": iso(10), **body}
    return client.post(f"{V1}/order-lines/{line.id}/booking", body, format="json")


def test_create_booking_after_payment(auth_api, paid_esim_line):
    r = book(auth_api, paid_esim_line)
    assert r.status_code == 201, r.content
    assert r.json()["booking_status"] == "confirmed" and r.json()["destination_country_codes"] == ["JP"]


def test_create_booking_twice_rejected(auth_api, paid_esim_line):
    book(auth_api, paid_esim_line)
    assert book(auth_api, paid_esim_line).status_code == 400


def test_create_booking_unpaid_rejected(auth_api, pending_esim_line):
    r = book(auth_api, pending_esim_line)
    assert r.status_code == 400 and r.json()["code"] == "order_not_paid"


def test_booking_start_in_past_rejected(auth_api, paid_esim_line):
    assert book(auth_api, paid_esim_line, start_at=iso(-2)).status_code == 400


def test_cannot_book_someone_elses_line(other_api, paid_esim_line):
    assert book(other_api, paid_esim_line).status_code == 404


def test_pack_destinations_on_create(auth_api, paid_pack_line):
    r = book(auth_api, paid_pack_line, destination_country_codes=["sg", "jp"])
    assert r.status_code == 201 and r.json()["destination_country_codes"] == ["JP", "SG"]
    assert book(auth_api, paid_pack_line, destination_country_codes=["FR"]).status_code == 400


def test_pocket_wifi_patch_locked(auth_api, order_factory):
    b = _paid(order_factory("wifi")).lines.get().booking
    r = auth_api.patch(f"{V1}/bookings/{b.id}", {"start_at": iso(4), "end_at": iso(6)}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "rental_dates_locked"


def test_patch_esim_dates(auth_api, paid_esim_line):
    bid = book(auth_api, paid_esim_line).json()["id"]
    r = auth_api.patch(f"{V1}/bookings/{bid}", {"start_at": iso(5), "end_at": iso(9)}, format="json")
    assert r.status_code == 200, r.content


def test_patch_after_start_rejected(auth_api, paid_esim_line):
    bid = book(auth_api, paid_esim_line).json()["id"]
    Booking.objects.filter(pk=bid).update(start_at=timezone.now() - timedelta(hours=1))
    r = auth_api.patch(f"{V1}/bookings/{bid}", {"end_at": iso(9)}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "booking_locked"


def test_pack_destinations_edit(auth_api, paid_pack_line):
    bid = book(auth_api, paid_pack_line).json()["id"]
    assert auth_api.patch(f"{V1}/bookings/{bid}", {"destination_country_codes": ["SG"]}, format="json").json()["destination_country_codes"] == ["SG"]
    assert auth_api.patch(f"{V1}/bookings/{bid}", {"destination_country_codes": ["FR"]}, format="json").status_code == 400


def test_bookings_private(auth_api, other_api, paid_esim_line):
    bid = book(auth_api, paid_esim_line).json()["id"]
    assert [b["id"] for b in auth_api.get(f"{V1}/bookings").json()["results"]] == [bid]
    assert other_api.get(f"{V1}/bookings").json()["results"] == []
    assert other_api.patch(f"{V1}/bookings/{bid}", {"end_at": iso(9)}, format="json").status_code == 404
