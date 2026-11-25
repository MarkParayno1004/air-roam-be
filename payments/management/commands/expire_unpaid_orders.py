import logging
from datetime import timedelta

import requests
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from orders.models import Order
from orders.status import transition
from payments import paymongo
from payments.settle import settle

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Expire orders left unpaid (PayMongo sessions never expire by themselves). Run hourly."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)

    def handle(self, *args, hours, **options):
        # all_objects: the checkout of a soft-deleted order can still be paid.
        for order in Order.all_objects.filter(order_status="pending_payment", created_at__lte=timezone.now() - timedelta(hours=hours)):
            try:
                close(order)
            except Exception:
                log.exception("could not expire unpaid order %s", order.id)


def close(order):
    if order.payment_session_id:
        try:
            paymongo.expire_checkout(order)
            closed = True
        except requests.HTTPError:  # refused, e.g. already expired or paid: the session itself tells
            closed = False
        session = paymongo.get_session(order.payment_session_id)
        if paymongo.paid_centavos(session):
            if settle(session) is None:
                raise RuntimeError(f"paid session {order.payment_session_id} does not match its order")
            return
        if not closed and session["attributes"].get("status") != "expired":
            raise RuntimeError(f"session {order.payment_session_id} is still open")
    with transaction.atomic():
        order = Order.all_objects.select_for_update().get(pk=order.pk)
        if order.order_status == "pending_payment":  # a webhook may have settled it meanwhile
            transition(order, "expired")
            order.save(update_fields=["order_status", "updated_at"])
