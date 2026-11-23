import pytest

from orders.models import Order

pytestmark = pytest.mark.django_db
S = "/api/v1/staff/orders"


def _paid(o):
    o.order_status = "paid"
    o.save()
    return o


def test_traveler_forbidden(auth_api, order_factory):
    order_factory()
    assert auth_api.get(S).status_code == 403


def test_marketing_reads_but_cannot_change(marketing_api, order_factory):
    o = order_factory()
    assert marketing_api.get(S).status_code == 200
    detail = marketing_api.get(f"{S}/{o.id}").json()
    assert detail["user"]["email"] == "traveler@example.com" and len(detail["lines"]) == 1
    assert marketing_api.patch(f"{S}/{o.id}", {"order_status": "cancelled"}, format="json").status_code == 403
    assert marketing_api.delete(f"{S}/{o.id}").status_code == 403


def test_admin_valid_transition(admin_api, order_factory):
    o = _paid(order_factory())
    r = admin_api.patch(f"{S}/{o.id}", {"order_status": "fulfilled"}, format="json")
    assert r.status_code == 200 and r.json()["order_status"] == "fulfilled"


def test_admin_invalid_transition(admin_api, order_factory):
    o = _paid(order_factory())
    r = admin_api.patch(f"{S}/{o.id}", {"order_status": "pending_payment"}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "invalid_transition"


def test_admin_cannot_patch_other_fields(admin_api, order_factory):
    o = order_factory()
    admin_api.patch(f"{S}/{o.id}", {"total_amount": "1.00"}, format="json")
    o.refresh_from_db()
    assert str(o.total_amount) == "799.00"


def test_order_filters(admin_api, order_factory, other_user):
    paid = _paid(order_factory())
    order_factory(owner=other_user)
    ids = lambda r: [x["id"] for x in r.json()["results"]]
    assert ids(admin_api.get(S, {"order_status": "paid"})) == [str(paid.id)]
    assert len(ids(admin_api.get(S, {"email": "other@"}))) == 1
    assert len(ids(admin_api.get(S, {"created_from": "2000-01-01", "created_to": "2999-01-01"}))) == 2


def test_admin_soft_deletes(admin_api, order_factory):
    o = order_factory()
    assert admin_api.delete(f"{S}/{o.id}").status_code == 204
    assert Order.all_objects.get(pk=o.pk).deleted_at is not None
    assert admin_api.get(f"{S}/{o.id}").status_code == 404
