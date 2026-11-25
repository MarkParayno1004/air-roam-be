import pytest
from django.db import IntegrityError

from catalog.models import active_regions, overlapping_region

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("mb,days,label", [(5120, 7, "5GB · 7 days"), (None, 30, "Unlimited · 30 days"), (512, 1, "0.5GB · 1 day"), (1280, 7, "1.25GB · 7 days"), (40, 7, "0.04GB · 7 days")])
def test_plan_label(plan_factory, mb, days, label):
    assert plan_factory(data_mb=mb, validity_days=days).label == label


@pytest.mark.parametrize("name,mb,label", [
    ("Regular", 1024, "Regular · 1GB/day"),
    ("Unlimited", None, "Unlimited"),
    ("UNLIMITED", None, "UNLIMITED"),
    ("Fast", None, "Fast · Unlimited"),
    ("1gb/day", 1024, "1gb/day"),
    ("Lite", 512, "Lite · 0.5GB/day"),
])
def test_wifi_plan_label(wifi_plan_factory, name, mb, label):
    assert wifi_plan_factory(name=name, data_mb=mb).label == label


@pytest.mark.parametrize("bad", [{"for_wifi": True, "validity_days": 7}, {"for_wifi": False, "validity_days": None}])
def test_only_wifi_plans_have_no_validity(plan_factory, bad):
    with pytest.raises(IntegrityError):
        plan_factory(**bad)


def test_region_countries_normalized(region_factory):
    assert region_factory(countries=["kr", "jp", "kr"]).countries == ["JP", "KR"]


def test_active_regions_ignores_inactive_and_deleted(region_factory):
    region_factory(name="Off", is_active=False)
    region_factory(name="Gone").soft_delete()
    live = region_factory(name="Live")
    assert list(active_regions()) == [live]


def test_overlapping_region(region_factory):
    r = region_factory(countries=["JP", "KR"])
    assert overlapping_region(["SG", "KR"]) == ("KR", r)
    assert overlapping_region(["KR"], exclude_pk=r.pk) is None
