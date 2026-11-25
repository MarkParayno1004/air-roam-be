from django.db.models import Prefetch
from django.utils.text import slugify
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog import cache
from catalog.models import Product, ProductType, RegionPlan, active_regions, country_name
from catalog.serializers import DestinationSerializer, PlanSerializer, ProductSerializer


class PublicMixin:
    permission_classes = [AllowAny]
    authentication_classes = []


class ProductListView(PublicMixin, generics.ListAPIView):
    serializer_class = ProductSerializer

    def get_queryset(self):
        p = self.request.query_params
        qs = Product.objects.filter(is_active=True)
        if p.get("product_type"):
            qs = qs.filter(product_type=p["product_type"])
        if p.get("search"):
            qs = qs.filter(product_name__icontains=p["search"])
        return qs

    def list(self, request, *args, **kwargs):
        key = "products:" + "&".join(f"{k}={v}" for k, v in sorted(request.query_params.items()))
        return Response(cache.get_or_build(key, lambda: super(ProductListView, self).list(request, *args, **kwargs).data))


class ProductDetailView(PublicMixin, generics.RetrieveAPIView):
    serializer_class = ProductSerializer
    queryset = Product.objects.filter(is_active=True)


def build_destinations():
    # shortcut: every country carries its plans, split into a detail endpoint past ~500KB
    types = set(Product.objects.filter(is_active=True).values_list("product_type", flat=True))
    sells_wifi, sells_plans = ProductType.POCKET_WIFI in types, bool(types - {ProductType.POCKET_WIFI})
    by_code = {}
    regions = active_regions().prefetch_related(Prefetch("plans", queryset=RegionPlan.objects.filter(is_active=True), to_attr="sold_plans"))
    for region in regions:
        plans = region.sold_plans if sells_plans else []
        rate = region.pocket_wifi_daily_rate if sells_wifi else None
        prices = [p.price for p in plans] + ([rate] if rate else [])
        if not prices:
            continue
        priced = {"from_price": min(prices), "pocket_wifi_daily_rate": rate, "plans": PlanSerializer(plans, many=True).data}
        for code in region.countries:
            name = country_name(code)
            # oldest region wins, like region_for_country
            by_code.setdefault(code, {"country_code": code, "country_name": name, "slug": slugify(name), **priced})
    return sorted(by_code.values(), key=lambda d: d["country_name"])


class DestinationsView(PublicMixin, APIView):
    @extend_schema(responses=DestinationSerializer(many=True))
    def get(self, request):
        return Response(cache.get_or_build("destinations", lambda: DestinationSerializer(build_destinations(), many=True).data))
