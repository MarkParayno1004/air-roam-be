import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from catalog.models import Product, ProductVariant

pytestmark = pytest.mark.django_db
S = "/api/v1/staff"


def _png(size=(10, 10)):
    buf = io.BytesIO()
    Image.new("RGB", size, "teal").save(buf, "PNG")
    return buf.getvalue()


def test_marketing_can_create_product_and_variant(marketing_api):
    r = marketing_api.post(f"{S}/products", {"product_name": "Asia eSIM", "product_type": "esim", "product_description": "x"}, format="json")
    assert r.status_code == 201, r.content
    pid = r.json()["id"]
    r = marketing_api.post(f"{S}/products/{pid}/variants", {"name": "Asia 2", "countries": ["kr", "jp"], "region": "asia", "price": "999.00", "pricing_unit": "per_plan"}, format="json")
    assert r.status_code == 201, r.content
    assert r.json()["countries"] == ["JP", "KR"] and r.json()["scope"] == "multi"


def test_invalid_countries_rejected(marketing_api, variant_factory):
    v = variant_factory()
    r = marketing_api.patch(f"{S}/products/{v.product_id}/variants/{v.id}", {"countries": ["xx"]}, format="json")
    assert r.status_code == 400 and "countries" in r.json()


def test_traveler_forbidden(auth_api):
    assert auth_api.get(f"{S}/products").status_code == 403


def test_staff_list_includes_inactive_and_filters(admin_api, variant_factory):
    variant_factory(name="Off", product_active=False)
    variant_factory(name="Pack", countries=["JP", "KR"], product_type="pocket_wifi")
    r = admin_api.get(f"{S}/products", {"is_active": "false"})
    assert [p["product_name"] for p in r.json()["results"]] == ["Air Roam eSIM"] and not r.json()["results"][0]["is_active"]
    r = admin_api.get(f"{S}/products", {"scope": "multi"})
    assert [p["product_type"] for p in r.json()["results"]] == ["pocket_wifi"]
    r = admin_api.get(f"{S}/products", {"country": "kr"})
    assert len(r.json()["results"]) == 1


def test_thumbnail_rejects_non_image_and_large(marketing_api, variant_factory, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    pid = variant_factory().product_id
    url = f"{S}/products/{pid}/thumbnail"
    r = marketing_api.post(url, {"file": SimpleUploadedFile("a.png", b"not an image", "image/png")}, format="multipart")
    assert r.status_code == 400
    big = SimpleUploadedFile("big.png", _png() + b"0" * (2 * 1024 * 1024), "image/png")
    assert marketing_api.post(url, {"file": big}, format="multipart").status_code == 400


def test_thumbnail_saved_with_uuid_name(marketing_api, variant_factory, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    pid = variant_factory().product_id
    r = marketing_api.post(f"{S}/products/{pid}/thumbnail", {"file": SimpleUploadedFile("My Photo.png", _png(), "image/png")}, format="multipart")
    assert r.status_code == 200, r.content
    name = Product.objects.get(pk=pid).product_thumbnail_img.name
    assert name.startswith("thumbnails/") and name.endswith(".png") and "My Photo" not in name


def test_delete_is_soft(marketing_api, variant_factory):
    v = variant_factory()
    assert marketing_api.delete(f"{S}/products/{v.product_id}/variants/{v.id}").status_code == 204
    assert ProductVariant.all_objects.get(pk=v.pk).deleted_at is not None
    assert marketing_api.delete(f"{S}/products/{v.product_id}").status_code == 204
    assert Product.all_objects.get(pk=v.product_id).deleted_at is not None
