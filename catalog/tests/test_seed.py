import pytest
from django.core.management import call_command

from catalog.models import ProductVariant

pytestmark = pytest.mark.django_db


def test_seed_demo_is_idempotent():
    call_command("seed_demo")
    n = ProductVariant.objects.count()
    call_command("seed_demo")
    assert ProductVariant.objects.count() == n
    names = set(ProductVariant.objects.values_list("name", flat=True))
    assert {"Japan 10GB · 7 days", "Asia 8 countries · 10GB · 15 days", "Japan Pocket WiFi Unlimited"} <= names
    assert ProductVariant.objects.filter(countries__len__gt=1).exists()
    assert ProductVariant.objects.filter(pricing_unit="per_day").exists()
