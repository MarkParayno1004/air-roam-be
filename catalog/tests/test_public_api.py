from decimal import Decimal

import pytest

from catalog import rebuild

pytestmark = pytest.mark.django_db
V1 = "/api/v1"


@pytest.fixture
def products(product_factory):
    return product_factory("esim"), product_factory("pocket_wifi")


def dest(api):
    return api.get(f"{V1}/destinations").json()


def test_destination_shape(api, plan_factory, wifi_plan_factory, region_factory, products):
    r = region_factory(name="Secret Zone", countries=["JP", "KR"])
    p = plan_factory(region=r)
    w = wifi_plan_factory(region=r, price=Decimal("350.00"))
    cheap = wifi_plan_factory(region=r, name="Regular", data_mb=1024, price=Decimal("200.00"))
    wifi_plan_factory(region=r, name="Off", price=Decimal("1.00"), is_active=False)
    res = api.get(f"{V1}/destinations")
    assert [d["country_code"] for d in res.json()] == ["JP", "KR"]
    assert res.json()[0] == {
        "country_code": "JP", "country_name": "Japan", "slug": "japan", "from_price": "200.00", "is_popular": False,
        "region": {"id": str(r.id), "name": "Secret Zone"},
        "plans": [{"id": str(p.id), "label": "5GB · 7 days", "data_mb": 5120, "validity_days": 7, "price": "399.00"}],
        "wifi_plans": [
            {"id": str(cheap.id), "name": "Regular", "label": "Regular · 1GB/day", "data_mb": 1024, "price": "200.00"},
            {"id": str(w.id), "name": "Unlimited", "label": "Unlimited", "data_mb": None, "price": "350.00"},
        ],
    }


def test_no_wifi_product_hides_wifi_plans(api, plan_factory, wifi_plan_factory, product_factory):
    wifi_plan_factory(region=plan_factory().region)
    product_factory("sim")
    d = dest(api)[0]
    assert d["wifi_plans"] == [] and d["from_price"] == "399.00"


def test_no_sim_product_hides_plans(api, plan_factory, wifi_plan_factory, product_factory):
    wifi_plan_factory(region=plan_factory().region)
    product_factory("pocket_wifi")
    product_factory("esim", is_active=False)
    d = dest(api)[0]
    assert d["plans"] == [] and d["from_price"] == "100.00"


def test_region_with_only_wifi_plans_is_listed(api, wifi_plan_factory, products):
    wifi_plan_factory()
    d = dest(api)[0]
    assert d["plans"] == [] and [p["label"] for p in d["wifi_plans"]] == ["Unlimited"] and d["from_price"] == "100.00"


def test_country_with_nothing_to_sell_is_left_out(api, region_factory, products):
    region_factory()
    assert dest(api) == []


@pytest.mark.parametrize("how", ["inactive", "deleted"])
def test_hidden_region_and_plan(api, plan_factory, region_factory, products, how):
    def hide(obj):
        if how == "deleted":
            return obj.soft_delete()
        obj.is_active = False
        obj.save()

    region = region_factory(countries=["JP"])
    keep = plan_factory(region=region)
    hide(plan_factory(region=region, validity_days=30))
    other = region_factory(name="NA", countries=["US"])
    hide(other)
    data = api.get(f"{V1}/destinations").json()
    assert [d["country_code"] for d in data] == ["JP"]
    assert [p["id"] for p in data[0]["plans"]] == [str(keep.id)]


def test_products_have_no_prices(api, product_factory):
    product_factory("esim")
    product_factory("sim", is_active=False)
    product_factory("sim", product_name="Gone").soft_delete()
    res = api.get(f"{V1}/products").json()
    assert res["count"] == 1
    assert set(res["results"][0]) == {"id", "product_name", "product_type", "product_thumbnail_img", "product_description"}


def test_products_filter_type_and_search(api, products):
    assert [p["product_type"] for p in api.get(f"{V1}/products", {"product_type": "esim"}).json()["results"]] == ["esim"]
    assert [p["product_type"] for p in api.get(f"{V1}/products", {"search": "WIFI"}).json()["results"]] == ["pocket_wifi"]
    assert api.get(f"{V1}/products/{products[0].id}").status_code == 200


def test_price_edits_clear_cache_and_call_hook(api, plan_factory, wifi_plan_factory, products, django_capture_on_commit_callbacks, monkeypatch):
    calls = []
    monkeypatch.setattr(rebuild, "trigger_rebuild", lambda: calls.append(1))
    plan = plan_factory()
    wifi = wifi_plan_factory(region=plan.region)
    dest(api)  # warm cache
    with django_capture_on_commit_callbacks(execute=True):
        wifi.price = Decimal("80.00")
        wifi.save()
    assert calls and dest(api)[0]["wifi_plans"][0]["price"] == "80.00"
    with django_capture_on_commit_callbacks(execute=True):
        plan.price = Decimal("299.00")
        plan.save()
    assert dest(api)[0]["plans"][0]["price"] == "299.00"


def test_rebuild_hook_posts_and_never_raises(settings, monkeypatch):
    settings.WEB_REBUILD_HOOK_URL = "https://hook.test/deploy"
    seen = []

    def boom(url, timeout):
        seen.append((url, timeout))
        raise OSError("down")

    monkeypatch.setattr(rebuild.requests, "post", boom)
    rebuild.trigger_rebuild()
    assert seen == [("https://hook.test/deploy", 5)]


def test_rebuild_hook_disabled_without_url(settings, monkeypatch):
    settings.WEB_REBUILD_HOOK_URL = ""
    monkeypatch.setattr(rebuild.requests, "post", lambda *a, **k: pytest.fail("called"))
    rebuild.trigger_rebuild()
