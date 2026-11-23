from django.utils import timezone

from common.errors import DomainError

ALLOWED = {
    "pending_payment": {"paid", "expired", "cancelled"},
    "paid": {"fulfilled", "refunded", "cancelled"},
}
ENDED = {"cancelled", "expired", "refunded"}


def transition(order, new_status):
    """Validate and apply a status change. Ending an order cancels its open bookings (saved immediately)."""
    if new_status not in ALLOWED.get(order.order_status, set()):
        raise DomainError("invalid_transition", f"An order can't go from {order.order_status} to {new_status}.")
    order.order_status = new_status
    if new_status == "paid":
        order.paid_at = timezone.now()
    if new_status in ENDED and not order._state.adding:  # only persisted orders have bookings
        from bookings.models import Booking

        Booking.objects.filter(order_line__order=order).exclude(booking_status="completed").update(booking_status="cancelled")
