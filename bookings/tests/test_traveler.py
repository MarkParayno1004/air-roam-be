import pytest

pytestmark = pytest.mark.django_db
V1 = "/api/v1"


def _paid(order):
    order.order_status = "paid"
    order.save()
    return order


def test_travelers_cannot_create_or_change_bookings(auth_api, order_factory):
    line = _paid(order_factory("wifi")).lines.get()
    assert auth_api.post(f"{V1}/order-lines/{line.id}/booking", {}, format="json").status_code == 404
    assert auth_api.patch(f"{V1}/bookings/{line.booking.id}", {}, format="json").status_code == 405


def test_esim_order_never_has_a_booking(auth_api, order_factory):
    _paid(order_factory())
    assert auth_api.get(f"{V1}/bookings").json()["results"] == []


def test_bookings_private(auth_api, other_api, order_factory):
    bid = str(_paid(order_factory("wifi")).lines.get().booking.id)
    assert [b["id"] for b in auth_api.get(f"{V1}/bookings").json()["results"]] == [bid]
    assert auth_api.get(f"{V1}/bookings/{bid}").status_code == 200
    assert other_api.get(f"{V1}/bookings").json()["results"] == []
    assert other_api.get(f"{V1}/bookings/{bid}").status_code == 404
