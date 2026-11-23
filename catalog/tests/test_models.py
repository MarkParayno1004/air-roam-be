import pytest
from django.core.exceptions import ValidationError

from catalog.models import ProductVariant, normalize_countries

pytestmark = pytest.mark.django_db


def test_countries_normalized_and_validated():
    assert normalize_countries(["jp", "KR", "jp", " sg "]) == ["JP", "KR", "SG"]
    for bad in ([], ["xx"], ["JPN"], [""]):
        with pytest.raises(ValidationError):
            normalize_countries(bad)


def test_variant_save_normalizes(variant_factory):
    v = variant_factory(countries=["kr", "jp", "kr"])
    v.refresh_from_db()
    assert v.countries == ["JP", "KR"]


def test_scope_single_and_multi(variant_factory):
    assert variant_factory(countries=["JP"]).scope == "single"
    assert variant_factory(countries=["JP", "KR"]).scope == "multi"


def test_is_sellable(variant_factory):
    assert variant_factory().is_sellable
    assert not variant_factory(product_active=False).is_sellable
    assert not variant_factory(is_active=False).is_sellable


def test_soft_deleted_variant_hidden(variant_factory):
    v = variant_factory()
    v.soft_delete()
    assert not ProductVariant.objects.filter(pk=v.pk).exists()
    assert ProductVariant.all_objects.filter(pk=v.pk).exists()
    assert not v.is_sellable


def test_soft_deleted_product_makes_variant_unsellable(variant_factory):
    v = variant_factory()
    v.product.soft_delete()
    v.refresh_from_db()
    assert not v.is_sellable
