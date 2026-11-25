import pytest
from django.db import connection

from orders.models import Order
from orders.staff_views import StaffOrderViewSet
from payments import paymongo

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
    o = _paid(order_factory())
    assert admin_api.delete(f"{S}/{o.id}").status_code == 204
    assert Order.all_objects.get(pk=o.pk).deleted_at is not None
    assert admin_api.get(f"{S}/{o.id}").status_code == 404


def test_unpaid_order_cannot_be_deleted(admin_api, order_factory):
    o = order_factory()
    r = admin_api.delete(f"{S}/{o.id}")
    assert r.status_code == 409 and r.json() == {"code": "invalid_transition", "detail": "Cancel the order first."}
    assert Order.objects.filter(pk=o.pk).exists()


@pytest.mark.parametrize("new", ["cancelled", "paid"])
def test_payment_between_read_and_lock_wins(api, admin_api, order_factory, pay_api, monkeypatch, new):
    o = order_factory()
    pay_api.checkout(o)
    read = StaffOrderViewSet.get_object

    def read_then_pay(view):
        order = read(view)
        pay_api.pay(o)
        assert pay_api.hook(api, o.payment_session_id).status_code == 200
        return order

    monkeypatch.setattr(StaffOrderViewSet, "get_object", read_then_pay)
    r = admin_api.patch(f"{S}/{o.id}", {"order_status": new}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "invalid_transition"
    o.refresh_from_db()
    assert o.order_status == "paid" and o.paid_at and not o.needs_attention
    assert pay_api.sessions["cs_1"]["attributes"]["status"] == "active"  # nothing was closed


@pytest.mark.parametrize("new", ["cancelled", "expired", "paid"])
def test_closing_a_pending_order_closes_its_session_outside_the_lock(admin_api, order_factory, pay_api, monkeypatch, new):
    o = order_factory()
    pay_api.checkout(o)
    depth, expire = len(connection.savepoint_ids), paymongo.expire_checkout

    def expire_unlocked(order):
        assert len(connection.savepoint_ids) == depth
        expire(order)

    monkeypatch.setattr(paymongo, "expire_checkout", expire_unlocked)
    r = admin_api.patch(f"{S}/{o.id}", {"order_status": new}, format="json")
    assert r.status_code == 200 and r.json()["order_status"] == new
    assert pay_api.sessions["cs_1"]["attributes"]["status"] == "expired"


def test_staff_change_survives_paymongo_failure(admin_api, order_factory, pay_api, caplog):
    o = order_factory()
    pay_api.checkout(o)
    pay_api.down = True
    assert admin_api.patch(f"{S}/{o.id}", {"order_status": "cancelled"}, format="json").status_code == 200
    o.refresh_from_db()
    assert o.order_status == "cancelled" and "could not expire paymongo session" in caplog.text


def test_later_staff_changes_do_not_call_paymongo(admin_api, order_factory, pay_api):
    o = _paid(order_factory())
    Order.objects.update(payment_session_id="cs_1")
    admin_api.patch(f"{S}/{o.id}", {"order_status": "fulfilled"}, format="json")
    assert pay_api.calls == []
