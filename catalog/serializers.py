from rest_framework import serializers

from catalog.models import Product, RegionPlan


class PlanSerializer(serializers.ModelSerializer):
    label = serializers.ReadOnlyField()

    class Meta:
        model = RegionPlan
        fields = ["id", "label", "data_mb", "validity_days", "price"]


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "product_name", "product_type", "product_thumbnail_img", "product_description"]


class DestinationSerializer(serializers.Serializer):
    """A country and what it costs there. Regions stay internal."""

    country_code = serializers.CharField()
    country_name = serializers.CharField()
    slug = serializers.CharField()
    from_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    pocket_wifi_daily_rate = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    plans = PlanSerializer(many=True)
