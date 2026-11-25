import pytest
from django.core.management import call_command

from catalog.models import Product, Region, RegionPlan

pytestmark = pytest.mark.django_db


def test_seed_demo_is_idempotent(api):
    call_command("seed_demo")
    call_command("seed_demo")
    assert (Region.objects.count(), RegionPlan.objects.count(), Product.objects.count()) == (3, 18, 3)
    japan = next(d for d in api.get("/api/v1/destinations").json() if d["slug"] == "japan")
    assert [p["label"] for p in japan["plans"]] == ["30GB · 3 days", "5GB · 7 days", "10GB · 14 days", "14GB · 30 days"]
    assert [(p["label"], p["price"]) for p in japan["wifi_plans"]] == [("Regular · 1GB/day", "60.00"), ("Unlimited", "100.00")]
