from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from bookings.models import Booking
from orders.models import Client, Order, OrderLine


class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ["id", "destination_country_codes", "start_at", "end_at", "booking_status", "created_at", "updated_at"]
        read_only_fields = fields  # output shape; marks fields required in the OpenAPI schema


class OrderLineSerializer(serializers.ModelSerializer):
    booking = serializers.SerializerMethodField()

    class Meta:
        model = OrderLine
        fields = [
            "id", "product_variant", "product_name_snapshot", "variant_name_snapshot", "product_type_snapshot",
            "pricing_unit_snapshot", "countries_snapshot", "quantity", "unit_price", "rental_days", "line_total", "booking",
        ]
        read_only_fields = fields

    @extend_schema_field(BookingSerializer(allow_null=True))
    def get_booking(self, line):
        b = getattr(line, "booking", None)
        return BookingSerializer(b).data if b else None


class OrderSerializer(serializers.ModelSerializer):
    lines = OrderLineSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "order_status", "client", "currency", "total_amount", "xendit_invoice_url", "paid_at", "created_at", "updated_at", "lines"]
        read_only_fields = fields


class PriceUpdateSerializer(serializers.Serializer):
    variant_id = serializers.UUIDField()
    name = serializers.CharField()
    old_unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    new_unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)


class RemovedLineSerializer(serializers.Serializer):
    variant_id = serializers.UUIDField()
    name = serializers.CharField(allow_blank=True)


class CheckoutResponseSerializer(serializers.Serializer):
    order = OrderSerializer()
    invoice_url = serializers.URLField()
    price_updates = PriceUpdateSerializer(many=True)
    removed_lines = RemovedLineSerializer(many=True)


class CheckoutLineSerializer(serializers.Serializer):
    variant_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=10)
    expected_unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    start_at = serializers.DateTimeField(required=False)
    end_at = serializers.DateTimeField(required=False)
    destination_country_codes = serializers.ListField(child=serializers.CharField(max_length=2), required=False)


class CheckoutSerializer(serializers.Serializer):
    client = serializers.ChoiceField(choices=Client.choices, default=Client.WEB)
    lines = CheckoutLineSerializer(many=True, allow_empty=False, max_length=20)
