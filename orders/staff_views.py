from django.db.models import Q
from drf_spectacular.utils import extend_schema, extend_schema_field, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.response import Response

from accounts.permissions import AdminWriteOtherwiseStaffRead
from orders.models import Order, OrderStatus
from orders.serializers import OrderSerializer
from orders.status import transition


class StaffOrderSerializer(OrderSerializer):
    user = serializers.SerializerMethodField()

    class Meta(OrderSerializer.Meta):
        fields = OrderSerializer.Meta.fields + ["user", "xendit_invoice_id", "needs_attention", "attention_note"]

    @extend_schema_field(
        inline_serializer("OrderCustomer", {k: serializers.CharField() for k in ("id", "email", "first_name", "last_name", "contact_no")})
    )
    def get_user(self, o):
        u = o.user
        return {"id": str(u.id), "email": u.email, "first_name": u.first_name, "last_name": u.last_name, "contact_no": u.contact_no}


class StatusInput(serializers.Serializer):
    order_status = serializers.ChoiceField(choices=OrderStatus.choices)


class StaffOrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [AdminWriteOtherwiseStaffRead]
    serializer_class = StaffOrderSerializer

    def get_queryset(self):
        p = self.request.query_params
        qs = Order.objects.select_related("user").prefetch_related("lines__booking")
        if p.get("order_status"):
            qs = qs.filter(order_status=p["order_status"])
        if p.get("needs_attention") in ("true", "false"):
            qs = qs.filter(needs_attention=p["needs_attention"] == "true")
        if p.get("created_from"):
            qs = qs.filter(created_at__date__gte=p["created_from"])
        if p.get("created_to"):
            qs = qs.filter(created_at__date__lte=p["created_to"])
        if p.get("email"):
            qs = qs.filter(user__email__icontains=p["email"])
        if p.get("search"):
            s = p["search"]
            qs = qs.filter(Q(user__email__icontains=s) | Q(user__last_name__icontains=s) | Q(lines__variant_name_snapshot__icontains=s)).distinct()
        return qs

    @extend_schema(request=StatusInput, responses=StaffOrderSerializer)
    def partial_update(self, request, pk=None):
        order = self.get_object()
        s = StatusInput(data=request.data)
        s.is_valid(raise_exception=True)
        transition(order, s.validated_data["order_status"])
        order.save(update_fields=["order_status", "paid_at", "updated_at"])
        return Response(self.get_serializer(order).data)

    def destroy(self, request, pk=None):
        self.get_object().soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
