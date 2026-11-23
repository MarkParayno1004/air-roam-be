from django.db.models import Prefetch, Q
from django.utils.text import slugify
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog import cache
from catalog.models import Product, ProductVariant, Region, country_name
from catalog.serializers import DestinationSerializer, PackGroupSerializer, PackSerializer, ProductSerializer


def sellable_variants():
    return ProductVariant.objects.filter(
        is_active=True, product__is_active=True, product__deleted_at__isnull=True
    ).select_related("product")


def filtered_variants(params):
    qs = sellable_variants()
    if params.get("country"):
        qs = qs.filter(countries__contains=[params["country"].strip().upper()])
    if params.get("scope") == "single":
        qs = qs.filter(countries__len=1)
    elif params.get("scope") == "multi":
        qs = qs.filter(countries__len__gt=1)
    if params.get("region"):
        qs = qs.filter(region=params["region"])
    if params.get("product_type"):
        qs = qs.filter(product__product_type=params["product_type"])
    if params.get("featured") == "true":
        qs = qs.filter(is_featured=True)
    if params.get("search"):
        s = params["search"]
        qs = qs.filter(Q(name__icontains=s) | Q(product__product_name__icontains=s))
    return qs


class PublicMixin:
    permission_classes = [AllowAny]
    authentication_classes = []


class ProductListView(PublicMixin, generics.ListAPIView):
    serializer_class = ProductSerializer

    def get_queryset(self):
        vqs = filtered_variants(self.request.query_params)
        return (
            Product.objects.filter(is_active=True, variants__in=vqs)
            .distinct()
            .prefetch_related(Prefetch("variants", queryset=vqs, to_attr="matching_variants"))
            .order_by("product_name")
        )

    def list(self, request, *args, **kwargs):
        key = "products:" + "&".join(f"{k}={v}" for k, v in sorted(request.query_params.items()))
        return Response(cache.get_or_build(key, lambda: super(ProductListView, self).list(request, *args, **kwargs).data))


class ProductDetailView(PublicMixin, generics.RetrieveAPIView):
    serializer_class = ProductSerializer

    def get_queryset(self):
        return Product.objects.filter(is_active=True).prefetch_related(
            Prefetch("variants", queryset=sellable_variants(), to_attr="matching_variants")
        )


def build_destinations():
    by_code = {}
    for v in sellable_variants():
        for code in v.countries:
            d = by_code.setdefault(code, {"single_region": None, "pack_region": None, "from_price": None, "packs": 0})
            d["from_price"] = v.price if d["from_price"] is None else min(d["from_price"], v.price)
            if v.scope == "multi":
                d["packs"] += 1
                d["pack_region"] = d["pack_region"] or v.region
            else:
                d["single_region"] = d["single_region"] or v.region
    out = []
    for code, d in by_code.items():
        name = country_name(code)
        out.append({
            "country_code": code,
            "country_name": name,
            "slug": slugify(name),
            "region": d["single_region"] or d["pack_region"],
            "from_price": f"{d['from_price']:.2f}",
            "multi_country_pack_count": d["packs"],
        })
    return sorted(out, key=lambda d: d["country_name"])


class DestinationsView(PublicMixin, APIView):
    @extend_schema(responses=DestinationSerializer(many=True))
    def get(self, request):
        return Response(cache.get_or_build("destinations", build_destinations))


def build_packs():
    order = [r.value for r in Region]
    packs = sorted(sellable_variants().filter(countries__len__gt=1), key=lambda v: (order.index(v.region), v.price))
    groups = {}
    for v in packs:
        groups.setdefault(v.region, []).append(PackSerializer(v).data)
    return [{"region": r, "packs": p} for r, p in groups.items()]


class MultiCountryPacksView(PublicMixin, APIView):
    @extend_schema(responses=PackGroupSerializer(many=True))
    def get(self, request):
        return Response(cache.get_or_build("packs", build_packs))
