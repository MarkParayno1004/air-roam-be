from rest_framework import serializers

from orders.serializers import BookingSerializer


class BookingDetailSerializer(BookingSerializer):
    order_id = serializers.UUIDField(source="order_line.order_id", read_only=True)
    order_line_id = serializers.UUIDField(source="order_line.id", read_only=True)
    variant_name = serializers.CharField(source="order_line.variant_name_snapshot", read_only=True)
    product_type = serializers.CharField(source="order_line.product_type_snapshot", read_only=True)
    pricing_unit = serializers.CharField(source="order_line.pricing_unit_snapshot", read_only=True)
    countries = serializers.ListField(child=serializers.CharField(), source="order_line.countries_snapshot", read_only=True)

    class Meta(BookingSerializer.Meta):
        fields = BookingSerializer.Meta.fields + ["order_id", "order_line_id", "variant_name", "product_type", "pricing_unit", "countries"]
