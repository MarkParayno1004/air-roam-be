import pytest

from catalog import rebuild
from catalog.models import PopularCountry

pytestmark = pytest.mark.django_db
URL = "/api/v1/staff/countries"


def save(client, **popular):
    return client.patch(URL, {"countries": [{"code": c, "is_popular": v} for c, v in popular.items()]}, format="json")


def flags(client):
    return {c["code"]: c["is_popular"] for c in client.get(URL).json()}


def test_lists_countries_of_active_regions(marketing_api, region_factory):
    region_factory(name="Asia 1", countries=["KR", "JP"])
    region_factory(name="Off", countries=["FR"], is_active=False)
    assert marketing_api.get(URL).json() == [
        {"code": "JP", "name": "Japan", "region": "Asia 1", "is_popular": False},
        {"code": "KR", "name": "South Korea", "region": "Asia 1", "is_popular": False},
    ]


def test_save_changes_only_the_sent_countries(marketing_api, region_factory):
    region_factory(countries=["JP", "KR"])
    other = region_factory(name="EU", countries=["FR"])
    assert save(marketing_api, JP=True, FR=True).status_code == 200
    other.is_active = False
    other.save()
    r = save(marketing_api, JP=False, KR=True)
    assert r.status_code == 200 and {c["code"]: c["is_popular"] for c in r.json()} == {"JP": False, "KR": True}
    other.is_active = True
    other.save()
    assert flags(marketing_api) == {"FR": True, "JP": False, "KR": True}  # a hidden country keeps its flag


def test_saving_twice_is_fine_and_codes_are_normalized(marketing_api, region_factory):
    region_factory()
    assert save(marketing_api, jp=True).status_code == 200
    assert save(marketing_api, JP=True).status_code == 200
    assert list(PopularCountry.objects.values_list("country_code", flat=True)) == ["JP"]


@pytest.mark.parametrize("body", [{}, {"countries": [{"code": "ZZ", "is_popular": True}]}, {"countries": [{"code": "JP"}]}])
def test_bad_input_rejected(marketing_api, body):
    assert marketing_api.patch(URL, body, format="json").status_code == 400
    assert PopularCountry.objects.count() == 0


def test_travelers_forbidden(auth_api, api):
    assert auth_api.get(URL).status_code == 403 and save(auth_api, JP=True).status_code == 403
    assert api.get(URL).status_code == 401


def test_store_sees_popular_after_save(api, marketing_api, plan_factory, product_factory, django_capture_on_commit_callbacks, monkeypatch):
    calls = []
    monkeypatch.setattr(rebuild, "trigger_rebuild", lambda: calls.append(1))
    plan_factory()
    product_factory("esim")
    assert api.get("/api/v1/destinations").json()[0]["is_popular"] is False  # warms the cache
    with django_capture_on_commit_callbacks(execute=True):
        save(marketing_api, JP=True)
    assert calls == [1]
    assert api.get("/api/v1/destinations").json()[0]["is_popular"] is True
