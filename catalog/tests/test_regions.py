import pytest

from catalog.models import overlapping_region, region_for_country

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("mb,days,label", [(5120, 7, "5GB · 7 days"), (None, 30, "Unlimited · 30 days"), (512, 1, "0.5GB · 1 day"), (1280, 7, "1.25GB · 7 days"), (40, 7, "0.04GB · 7 days")])
def test_plan_label(plan_factory, mb, days, label):
    assert plan_factory(data_mb=mb, validity_days=days).label == label


def test_region_countries_normalized(region_factory):
    assert region_factory(countries=["kr", "jp", "kr"]).countries == ["JP", "KR"]


def test_region_for_country_ignores_inactive_and_deleted(region_factory):
    region_factory(name="Off", is_active=False)
    region_factory(name="Gone").soft_delete()
    live = region_factory(name="Live")
    assert region_for_country("JP") == live and region_for_country("FR") is None


def test_overlapping_region(region_factory):
    r = region_factory(countries=["JP", "KR"])
    assert overlapping_region(["SG", "KR"]) == ("KR", r)
    assert overlapping_region(["KR"], exclude_pk=r.pk) is None
