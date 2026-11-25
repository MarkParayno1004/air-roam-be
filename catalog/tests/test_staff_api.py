import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from catalog.models import Product

pytestmark = pytest.mark.django_db
S = "/api/v1/staff"


def _png(size=(10, 10)):
    buf = io.BytesIO()
    Image.new("RGB", size, "teal").save(buf, "PNG")
    return buf.getvalue()


def test_marketing_creates_product_without_prices(marketing_api):
    r = marketing_api.post(f"{S}/products", {"product_name": "Asia eSIM", "product_type": "esim", "product_description": "x"}, format="json")
    assert r.status_code == 201, r.content
    assert not {"variants", "price", "data_mb", "validity_days"} & set(r.json())


def test_traveler_forbidden(auth_api):
    assert auth_api.get(f"{S}/products").status_code == 403


def test_staff_list_includes_inactive_and_filters(admin_api, product_factory):
    product_factory("esim", is_active=False)
    product_factory("pocket_wifi")
    types = lambda **q: [p["product_type"] for p in admin_api.get(f"{S}/products", q).json()["results"]]
    assert types() == ["esim", "pocket_wifi"]
    assert types(is_active="false") == ["esim"]
    assert types(product_type="pocket_wifi") == ["pocket_wifi"]
    assert types(search="wifi") == ["pocket_wifi"]


def test_thumbnail_rejects_non_image_and_large(marketing_api, product_factory, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    pid = product_factory().id
    url = f"{S}/products/{pid}/thumbnail"
    r = marketing_api.post(url, {"file": SimpleUploadedFile("a.png", b"not an image", "image/png")}, format="multipart")
    assert r.status_code == 400
    big = SimpleUploadedFile("big.png", _png() + b"0" * (2 * 1024 * 1024), "image/png")
    assert marketing_api.post(url, {"file": big}, format="multipart").status_code == 400


def test_thumbnail_saved_with_uuid_name(marketing_api, product_factory, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    pid = product_factory().id
    r = marketing_api.post(f"{S}/products/{pid}/thumbnail", {"file": SimpleUploadedFile("My Photo.png", _png(), "image/png")}, format="multipart")
    assert r.status_code == 200, r.content
    name = Product.objects.get(pk=pid).product_thumbnail_img.name
    assert name.startswith("thumbnails/") and name.endswith(".png") and "My Photo" not in name


def test_delete_is_soft(marketing_api, product_factory):
    p = product_factory()
    assert marketing_api.delete(f"{S}/products/{p.id}").status_code == 204
    assert Product.all_objects.get(pk=p.pk).deleted_at is not None
