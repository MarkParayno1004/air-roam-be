from decimal import Decimal

import pytest

from catalog import rebuild

pytestmark = pytest.mark.django_db
V1 = "/api/v1"


@pytest.fixture
def catalog(variant_factory):
    jp = variant_factory(name="Japan 3GB 5 days", price=Decimal("449.00"))
    asia = variant_factory(name="Asia 8 countries", countries=["JP", "KR", "MY"], price=Decimal("1299.00"), tag="Best value")
    fr = variant_factory(name="France 10GB", countries=["FR"], region="europe", price=Decimal("799.00"), is_featured=True)
    eu = variant_factory(name="Europe 33", countries=["FR", "DE"], region="europe", price=Decimal("2499.00"))
    off = variant_factory(name="Japan old", price=Decimal("10.00"), is_active=False)
    return {"jp": jp, "asia": asia, "fr": fr, "eu": eu, "off": off}


def _variant_names(resp):
    return sorted(v["name"] for p in resp.json()["results"] for v in p["variants"])


def test_products_public_and_paginated(api, catalog):
    r = api.get(f"{V1}/products")
    assert r.status_code == 200 and "count" in r.json()


def test_products_filter_country_includes_packs(api, catalog):
    r = api.get(f"{V1}/products", {"country": "jp"})
    assert _variant_names(r) == ["Asia 8 countries", "Japan 3GB 5 days"]
    v = next(v for p in r.json()["results"] for v in p["variants"] if v["name"] == "Asia 8 countries")
    assert v["scope"] == "multi" and v["countries"] == ["JP", "KR", "MY"]


def test_products_scope_filter(api, catalog):
    assert _variant_names(api.get(f"{V1}/products", {"scope": "multi"})) == ["Asia 8 countries", "Europe 33"]


def test_products_region_featured_search(api, catalog):
    assert _variant_names(api.get(f"{V1}/products", {"region": "europe"})) == ["Europe 33", "France 10GB"]
    assert _variant_names(api.get(f"{V1}/products", {"featured": "true"})) == ["France 10GB"]
    assert _variant_names(api.get(f"{V1}/products", {"search": "asia"})) == ["Asia 8 countries"]


def test_inactive_variant_hidden(api, catalog):
    assert "Japan old" not in _variant_names(api.get(f"{V1}/products"))


def test_inactive_product_hidden(api, variant_factory):
    variant_factory(name="Hidden", product_active=False)
    assert _variant_names(api.get(f"{V1}/products")) == []


def test_destinations_from_price_and_pack_count(api, catalog):
    r = api.get(f"{V1}/destinations")
    assert r.status_code == 200
    by = {d["country_code"]: d for d in r.json()}
    assert by["JP"] == {"country_code": "JP", "country_name": "Japan", "slug": "japan", "region": "asia", "from_price": "449.00", "multi_country_pack_count": 1}
    assert by["MY"]["from_price"] == "1299.00" and by["MY"]["region"] == "asia"  # only via the pack
    assert by["FR"]["multi_country_pack_count"] == 1


def test_multi_country_packs_grouped_by_region(api, catalog):
    r = api.get(f"{V1}/multi-country-packs")
    groups = {g["region"]: g["packs"] for g in r.json()}
    assert [p["name"] for p in groups["asia"]] == ["Asia 8 countries"]
    assert groups["asia"][0]["countries"][0] == {"code": "JP", "name": "Japan"}
    assert groups["asia"][0]["product_type"] == "esim"
    assert set(groups) == {"asia", "europe"}


def test_catalog_save_clears_cache_and_calls_hook(api, settings, variant_factory, django_capture_on_commit_callbacks, monkeypatch):
    calls = []
    monkeypatch.setattr(rebuild, "trigger_rebuild", lambda: calls.append(1))
    v = variant_factory(name="Japan 3GB", price=Decimal("449.00"))
    api.get(f"{V1}/destinations")  # warm cache
    with django_capture_on_commit_callbacks(execute=True):
        v.price = Decimal("399.00")
        v.save()
    assert calls
    assert api.get(f"{V1}/destinations").json()[0]["from_price"] == "399.00"


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
