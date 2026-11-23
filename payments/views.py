import hmac
import logging
import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.models import Booking
from orders.models import Order
from orders.status import transition

log = logging.getLogger(__name__)


@extend_schema(exclude=True)  # called by Xendit, not by our clients
class XenditWebhookView(APIView):
    """Invoice callback. Token-verified, amount-checked, idempotent (repeats and late events are no-ops)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def post(self, request):
        expected = settings.XENDIT_CALLBACK_TOKEN
        got = request.headers.get("x-callback-token", "")
        if not expected or not hmac.compare_digest(got, expected):
            return Response({"detail": "Invalid callback token."}, status=403)

        data = request.data
        try:
            amount = Decimal(str(data.get("paid_amount", data.get("amount"))))
        except (InvalidOperation, TypeError):
            return Response({"detail": "Missing amount."}, status=400)

        with transaction.atomic():
            order = Order.all_objects.select_for_update().filter(pk=data.get("external_id")).first() if _is_uuid(data.get("external_id")) else None
            if order is None:
                return Response({"detail": "Unknown order."}, status=404)
            if amount != order.total_amount:
                return Response({"detail": "Amount does not match the order."}, status=400)
            status = data.get("status")
            if order.order_status != "pending_payment":
                if status == "PAID" and order.order_status != "paid":
                    # Money arrived for an order we already closed: never drop it silently.
                    order.needs_attention = True
                    order.attention_note = (
                        f"Paid via Xendit invoice {data.get('id', '')} after the order was {order.order_status}. "
                        "Refund the traveler or reinstate the order."
                    )
                    order.save(update_fields=["needs_attention", "attention_note", "updated_at"])
                    log.error("payment received for %s order %s", order.order_status, order.id)
                return Response({"status": "ignored"})
            if status == "PAID":
                transition(order, "paid")
                order.save(update_fields=["order_status", "paid_at", "updated_at"])
                Booking.objects.filter(order_line__order=order, booking_status="pending").update(booking_status="confirmed")
            elif status == "EXPIRED":
                transition(order, "expired")
                order.save(update_fields=["order_status", "updated_at"])
        return Response({"status": "ok"})


def _is_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False
