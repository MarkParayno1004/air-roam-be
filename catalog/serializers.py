from rest_framework import serializers

from catalog.models import Product, RegionPlan


class PlanSerializer(serializers.ModelSerializer):
    label = serializers.ReadOnlyField()
    validity_days = serializers.IntegerField()  # only Pocket WiFi plans have none

    class Meta:
        model = RegionPlan
        fields = ["id", "label", "data_mb", "validity_days", "price"]


class WifiPlanSerializer(serializers.ModelSerializer):
    label = serializers.ReadOnlyField()

    class Meta:
        model = RegionPlan
        fields = ["id", "name", "label", "data_mb", "price"]
        read_only_fields = fields  # output shape; marks fields required in the OpenAPI schema


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "product_name", "product_type", "product_thumbnail_img", "product_description"]


class DestinationRegionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class DestinationSerializer(serializers.Serializer):
    """A country, its price region and what it costs there."""

    region = DestinationRegionSerializer()

    country_code = serializers.CharField()
    country_name = serializers.CharField()
    slug = serializers.CharField()
    from_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    plans = PlanSerializer(many=True)
    wifi_plans = WifiPlanSerializer(many=True)
    is_popular = serializers.BooleanField()
