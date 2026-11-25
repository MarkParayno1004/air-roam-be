from datetime import timedelta

import pytest
from django.utils import timezone

pytestmark = pytest.mark.django_db
S = "/api/v1/staff/bookings"


def iso(days):
    return (timezone.now() + timedelta(days=days)).isoformat()


@pytest.fixture
def wifi_booking(order_factory):
    o = order_factory("wifi", nights=6)
    o.order_status = "paid"
    o.save()
    return o.lines.get().booking


def test_marketing_reads_but_cannot_edit(marketing_api, wifi_booking):
    r = marketing_api.get(S)
    assert r.status_code == 200 and (r.json()["results"][0]["product_name"], r.json()["results"][0]["variant_name"]) == ("Air Roam pocket_wifi", "Japan")
    assert marketing_api.patch(f"{S}/{wifi_booking.id}", {"booking_status": "active"}, format="json").status_code == 403


def test_admin_changes_pocket_wifi_dates(admin_api, wifi_booking):
    same = admin_api.patch(f"{S}/{wifi_booking.id}", {"start_at": iso(4), "end_at": iso(10)}, format="json")
    assert same.status_code == 200, same.content
    assert same.json()["rental_days_changed"] is False
    longer = admin_api.patch(f"{S}/{wifi_booking.id}", {"end_at": iso(12)}, format="json")
    assert longer.status_code == 200 and longer.json()["rental_days_changed"] is True


def test_admin_status_and_destinations(admin_api, wifi_booking):
    r = admin_api.patch(f"{S}/{wifi_booking.id}", {"booking_status": "active", "destination_country_codes": ["jp"]}, format="json")
    assert r.status_code == 200 and r.json()["booking_status"] == "active"
    assert admin_api.patch(f"{S}/{wifi_booking.id}", {"destination_country_codes": ["FR"]}, format="json").status_code == 400
    assert admin_api.patch(f"{S}/{wifi_booking.id}", {"booking_status": "nope"}, format="json").status_code == 400


def test_admin_rejects_end_before_start(admin_api, wifi_booking):
    assert admin_api.patch(f"{S}/{wifi_booking.id}", {"start_at": iso(9), "end_at": iso(5)}, format="json").status_code == 400


def test_booking_filters(admin_api, wifi_booking):
    ids = lambda r: [x["id"] for x in r.json()["results"]]
    assert ids(admin_api.get(S, {"country": "jp"})) == [str(wifi_booking.id)]
    assert ids(admin_api.get(S, {"country": "FR"})) == []
    assert ids(admin_api.get(S, {"booking_status": "pending"})) == [str(wifi_booking.id)]
    day = timezone.localtime(wifi_booking.start_at).date().isoformat()
    assert ids(admin_api.get(S, {"start_from": day, "start_to": day})) == [str(wifi_booking.id)]
