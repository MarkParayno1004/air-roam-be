import logging

from django.db import transaction

from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.errors import DomainError
from orders.checkout import create_order
from orders.models import Order
from orders.serializers import CheckoutResponseSerializer, CheckoutSerializer, OrderSerializer
from orders.status import transition

log = logging.getLogger(__name__)


def order_queryset():
    return Order.objects.prefetch_related("lines__booking")


class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = OrderSerializer
    lookup_value_converter = "uuid"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation has no user
            return Order.objects.none()
        return order_queryset().filter(user=self.request.user)

    @extend_schema(request=CheckoutSerializer, responses={201: CheckoutResponseSerializer})
    def create(self, request):
        s = CheckoutSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        result = create_order(request.user, s.validated_data["client"], s.validated_data["lines"])
        order = result.order
        from payments import paymongo  # resolved at call time so tests can swap the client

        try:
            _, invoice_url = paymongo.create_checkout(order)
        except Exception:
            log.exception("paymongo checkout failed for order %s", order.id)
            transition(order, "cancelled")
            order.save(update_fields=["order_status", "updated_at"])
            raise DomainError("payment_provider_unavailable", "We couldn't reach the payment provider. Please try again.", status=502)
        return Response(
            {
                "order": OrderSerializer(order_queryset().get(pk=order.pk)).data,
                "invoice_url": invoice_url,
                "price_updates": result.price_updates,
                "removed_lines": result.removed_lines,
            },
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=None, responses=OrderSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        self.get_object()  # ownership check (404 for others)
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=pk)  # serialize against a concurrent paid webhook
            if order.order_status != "pending_payment":
                raise DomainError("invalid_transition", "Only unpaid orders can be cancelled.")
            transition(order, "cancelled")
            order.save(update_fields=["order_status", "updated_at"])
        from payments import paymongo

        try:
            paymongo.expire_checkout(order)  # so the session can't be paid any more
        except Exception:
            log.exception("could not expire paymongo session for cancelled order %s", order.id)
            with transaction.atomic():
                order = Order.all_objects.select_for_update().get(pk=pk)  # fresh: a webhook may have added its own note
                order.flag(
                    f"Cancelled by the traveler, but its PayMongo page could not be closed (session {order.payment_session_id}). "
                    "Check it in the PayMongo dashboard."
                )
                order.save(update_fields=["needs_attention", "attention_note", "updated_at"])
        return Response(OrderSerializer(order_queryset().get(pk=order.pk)).data)
