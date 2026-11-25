import logging

from django.db import transaction

from bookings.models import Booking
from orders.models import Order
from orders.status import transition
from payments.paymongo import paid_centavos, total_centavos

log = logging.getLogger(__name__)


@transaction.atomic
def settle(session):
    """Apply a paid PayMongo session (as fetched from PayMongo) to its order. Returns the order, or None when no order matches."""
    order = Order.all_objects.select_for_update().filter(payment_session_id=session["id"]).first()
    if order is None or str(order.id) != session["attributes"].get("reference_number"):
        return None
    received = paid_centavos(session)
    if received <= (order.received_centavos or 0):  # already handled, whatever happened to the order since; a lower amount is a stale read or a refund
        return order
    order.received_centavos = received
    exact = received == total_centavos(order)
    if exact and order.order_status == "pending_payment":
        transition(order, "paid")
        Booking.objects.filter(order_line__order=order, booking_status="pending").update(booking_status="confirmed")
    else:
        # Money we can't match to an open order: never drop it silently.
        problem = f"after the order was {order.order_status}" if exact else f"but the order total is PHP {order.total_amount} (order was {order.order_status})"
        order.flag(
            f"Paid PHP {received // 100}.{received % 100:02d} via PayMongo session {session['id']} {problem}. "
            "Check the payment in the PayMongo dashboard, then refund the traveler there or handle the order manually."
        )
    if order.deleted_at:
        order.deleted_at = None  # staff can't see deleted orders
        order.flag(f"This deleted order was paid via PayMongo session {session['id']}, so it was restored.")
    if order.needs_attention:
        log.error("order %s needs attention: %s", order.id, order.attention_note)
    order.save(update_fields=["order_status", "paid_at", "received_centavos", "needs_attention", "attention_note", "deleted_at", "updated_at"])
    return order
