import pytest

from catalog.models import RegionPlan

pytestmark = pytest.mark.django_db
S = "/api/v1/staff"


def test_create_region_and_plan(marketing_api):
    r = marketing_api.post(f"{S}/regions", {"name": "Asia 1", "countries": ["kr", "jp"], "pocket_wifi_daily_rate": "100.00"}, format="json")
    assert r.status_code == 201, r.content
    assert r.json()["countries"] == ["JP", "KR"] and r.json()["plans"] == []
    p = marketing_api.post(f"{S}/regions/{r.json()['id']}/plans", {"data_mb": 5120, "validity_days": 7, "price": "399.00"}, format="json")
    assert p.status_code == 201 and p.json()["label"] == "5GB · 7 days"
    assert [x["id"] for x in marketing_api.get(f"{S}/regions/{r.json()['id']}").json()["plans"]] == [p.json()["id"]]


def test_unknown_country_rejected(marketing_api):
    r = marketing_api.post(f"{S}/regions", {"name": "X", "countries": ["xx"]}, format="json")
    assert r.status_code == 400 and "countries" in r.json()


def test_country_in_another_active_region_rejected(marketing_api, region_factory):
    region_factory(name="Asia 1", countries=["JP"])
    r = marketing_api.post(f"{S}/regions", {"name": "Asia 2", "countries": ["KR", "JP"]}, format="json")
    assert r.status_code == 400 and r.json()["countries"] == ["Japan is already in region Asia 1."]


def test_reactivating_overlapping_region_rejected(marketing_api, region_factory):
    region_factory(name="Asia 1")
    off = region_factory(name="Asia 2", is_active=False)
    assert marketing_api.patch(f"{S}/regions/{off.id}", {"is_active": True}, format="json").status_code == 400
    assert marketing_api.patch(f"{S}/regions/{off.id}", {"name": "Asia 3"}, format="json").status_code == 200  # still inactive: fine


def test_editing_region_does_not_clash_with_itself(marketing_api, region_factory):
    r = region_factory()
    assert marketing_api.patch(f"{S}/regions/{r.id}", {"countries": ["JP", "KR"]}, format="json").status_code == 200


@pytest.mark.parametrize("bad", [{"price": "0"}, {"price": "-1"}, {"validity_days": 0}, {"data_mb": 0}])
def test_bad_plan_values(marketing_api, plan_factory, bad):
    p = plan_factory()
    r = marketing_api.patch(f"{S}/regions/{p.region_id}/plans/{p.id}", bad, format="json")
    assert r.status_code == 400 and next(iter(bad)) in r.json()


def test_wifi_rate_optional_but_positive(marketing_api, region_factory):
    url = f"{S}/regions/{region_factory().id}"
    assert marketing_api.patch(url, {"pocket_wifi_daily_rate": None}, format="json").status_code == 200
    assert marketing_api.patch(url, {"pocket_wifi_daily_rate": "0"}, format="json").status_code == 400


def test_region_search(marketing_api, region_factory):
    region_factory(name="Asia 1")
    region_factory(name="Europe", countries=["FR"])
    assert [r["name"] for r in marketing_api.get(f"{S}/regions", {"search": "eur"}).json()["results"]] == ["Europe"]


def test_deletes_are_soft_and_travelers_forbidden(marketing_api, auth_api, plan_factory):
    p = plan_factory()
    assert auth_api.get(f"{S}/regions").status_code == 403
    assert marketing_api.delete(f"{S}/regions/{p.region_id}/plans/{p.id}").status_code == 204
    assert marketing_api.get(f"{S}/regions/{p.region_id}").json()["plans"] == []
    assert marketing_api.delete(f"{S}/regions/{p.region_id}").status_code == 204
    assert RegionPlan.all_objects.filter(pk=p.pk).exists()
