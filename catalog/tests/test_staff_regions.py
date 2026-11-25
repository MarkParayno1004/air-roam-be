import pytest

from catalog.models import RegionPlan

pytestmark = pytest.mark.django_db
S = "/api/v1/staff"


def test_create_region_and_plan(marketing_api):
    r = marketing_api.post(f"{S}/regions", {"name": "Asia 1", "countries": ["kr", "jp"]}, format="json")
    assert r.status_code == 201, r.content
    assert r.json()["countries"] == ["JP", "KR"] and r.json()["plans"] == []
    p = marketing_api.post(f"{S}/regions/{r.json()['id']}/plans", {"data_mb": 5120, "validity_days": 7, "price": "399.00"}, format="json")
    assert p.status_code == 201 and p.json()["label"] == "5GB · 7 days" and p.json()["for_wifi"] is False
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


def add(client, region, **body):
    return client.post(f"{S}/regions/{region.id}/plans", {"price": "200.00", **body}, format="json")


def wifi(client, region, **body):
    return add(client, region, **{"for_wifi": True, "name": "Regular", "data_mb": 1024, **body})


def edit(client, plan, **body):
    return client.patch(f"{S}/regions/{plan.region_id}/plans/{plan.id}", body, format="json")


def test_create_wifi_plan(marketing_api, region_factory):
    region = region_factory()
    r = wifi(marketing_api, region, validity_days=None)
    assert r.status_code == 201, r.content
    assert {k: r.json()[k] for k in ("label", "name", "for_wifi", "data_mb", "validity_days", "price")} == {
        "label": "Regular · 1GB/day", "name": "Regular", "for_wifi": True, "data_mb": 1024, "validity_days": None, "price": "200.00",
    }
    assert wifi(marketing_api, region, name="Unlimited", data_mb=None).json()["label"] == "Unlimited"


@pytest.mark.parametrize("bad,field", [({"name": ""}, "name"), ({"name": "  "}, "name"), ({"validity_days": 7}, "validity_days"), ({"price": "0"}, "price"), ({"data_mb": 0}, "data_mb")])
def test_bad_wifi_plan_rejected(marketing_api, region_factory, wifi_plan_factory, bad, field):
    region = region_factory()
    r = wifi(marketing_api, region, **bad)
    assert r.status_code == 400 and list(r.json()) == [field]
    r = edit(marketing_api, wifi_plan_factory(region=region), **bad)
    assert r.status_code == 400 and list(r.json()) == [field]


def test_wifi_plan_needs_a_name(marketing_api, region_factory):
    r = add(marketing_api, region_factory(), for_wifi=True)
    assert r.status_code == 400 and list(r.json()) == ["name"]


def test_sim_plan_needs_validity_and_drops_the_name(marketing_api, region_factory, plan_factory):
    region = region_factory()
    for body in ({}, {"validity_days": None}):
        r = add(marketing_api, region, **body)
        assert r.status_code == 400 and list(r.json()) == ["validity_days"]
    p = add(marketing_api, region, validity_days=7, name="Regular")
    assert p.status_code == 201 and p.json()["name"] == "" and p.json()["label"] == "Unlimited · 7 days"
    plan = plan_factory(region=region)
    assert list(edit(marketing_api, plan, validity_days=None).json()) == ["validity_days"]
    assert edit(marketing_api, plan, name="X", price="5.00").json()["name"] == ""


def test_plan_kind_cannot_change(marketing_api, plan_factory, wifi_plan_factory):
    sim = plan_factory()
    wf = wifi_plan_factory(region=sim.region)
    for r in (edit(marketing_api, sim, for_wifi=True, name="X", validity_days=None), edit(marketing_api, wf, for_wifi=False, validity_days=7)):
        assert r.status_code == 400 and list(r.json()) == ["for_wifi"]
    assert edit(marketing_api, sim, for_wifi=False).status_code == 200
    assert edit(marketing_api, wf, for_wifi=True, price="90.00").status_code == 200


def test_wifi_plan_names_unique_per_region(marketing_api, region_factory, wifi_plan_factory):
    region, other = region_factory(), region_factory(name="NA", countries=["US"])
    first = wifi_plan_factory(region=region, name="Regular", is_active=False)
    second = wifi_plan_factory(region=region, name="Unlimited")
    for r in (wifi(marketing_api, region, name="regular "), edit(marketing_api, second, name="REGULAR")):
        assert r.status_code == 400 and list(r.json()) == ["name"]
    assert edit(marketing_api, first, name="REGULAR").status_code == 200
    assert wifi(marketing_api, other).status_code == 201
    first.soft_delete()
    assert wifi(marketing_api, region).status_code == 201


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
