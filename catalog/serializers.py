from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from catalog.models import Product, ProductVariant, country_name

VARIANT_FIELDS = [
    "id", "name", "countries", "scope", "region", "tag", "is_featured",
    "data_mb", "validity_days", "price", "pricing_unit",
]


class VariantSerializer(serializers.ModelSerializer):
    scope = serializers.ReadOnlyField()

    class Meta:
        model = ProductVariant
        fields = VARIANT_FIELDS


class ProductSerializer(serializers.ModelSerializer):
    variants = VariantSerializer(many=True, source="matching_variants")

    class Meta:
        model = Product
        fields = ["id", "product_name", "product_type", "product_thumbnail_img", "product_description", "variants"]


class DestinationSerializer(serializers.Serializer):
    country_code = serializers.CharField()
    country_name = serializers.CharField()
    slug = serializers.CharField()
    region = serializers.CharField()
    from_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    multi_country_pack_count = serializers.IntegerField()


class PackCountrySerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class PackSerializer(VariantSerializer):
    product_type = serializers.CharField(source="product.product_type")
    product_name = serializers.CharField(source="product.product_name")
    countries = serializers.SerializerMethodField()

    class Meta(VariantSerializer.Meta):
        fields = VARIANT_FIELDS + ["product_type", "product_name"]

    @extend_schema_field(PackCountrySerializer(many=True))
    def get_countries(self, v):
        return [{"code": c, "name": country_name(c)} for c in v.countries]


class PackGroupSerializer(serializers.Serializer):
    region = serializers.CharField()
    packs = PackSerializer(many=True)
