import pytest

from common.errors import DomainError
from orders.models import Order
from orders.status import transition


@pytest.mark.parametrize(
    "start,end",
    [("pending_payment", "paid"), ("pending_payment", "expired"), ("pending_payment", "cancelled"),
     ("paid", "fulfilled"), ("paid", "refunded"), ("paid", "cancelled")],
)
def test_allowed(start, end):
    o = Order(order_status=start)
    transition(o, end)
    assert o.order_status == end


def test_paid_sets_paid_at():
    o = Order(order_status="pending_payment")
    transition(o, "paid")
    assert o.paid_at is not None


@pytest.mark.parametrize("start,end", [("paid", "pending_payment"), ("expired", "paid"), ("cancelled", "paid"), ("fulfilled", "refunded"), ("paid", "paid")])
def test_rejected(start, end):
    with pytest.raises(DomainError) as e:
        transition(Order(order_status=start), end)
    assert e.value.code == "invalid_transition"
