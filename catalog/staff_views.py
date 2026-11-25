import uuid

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsMarketingOrAdmin
from catalog import signals
from catalog.models import PopularCountry, Product, Region, RegionPlan, active_regions, country_name, normalize_countries, overlapping_region

MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024
IMAGE_EXT = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp", "GIF": "gif"}


class StaffPlanSerializer(serializers.ModelSerializer):
    label = serializers.ReadOnlyField()

    class Meta:
        model = RegionPlan
        fields = ["id", "label", "for_wifi", "name", "data_mb", "validity_days", "price", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        current = self.instance
        wifi = attrs.get("for_wifi", current.for_wifi if current else False)
        name = attrs.get("name", current.name if current else "")
        days = attrs.get("validity_days", current.validity_days if current else None)
        if current and wifi != current.for_wifi:
            raise serializers.ValidationError({"for_wifi": ["A plan can't change between SIM/eSIM and Pocket WiFi."]})
        if not wifi:
            if days is None:
                raise serializers.ValidationError({"validity_days": ["This field is required."]})
            return attrs | {"name": ""}
        errors = {}
        if days is not None:
            errors["validity_days"] = ["Pocket WiFi plans are priced per day and have no validity."]
        if not name:
            errors["name"] = ["This field is required."]
        # shortcut: name checked here only, add a partial unique constraint if staff edit plans concurrently
        elif RegionPlan.objects.filter(region=self.context["view"].kwargs["region_pk"], for_wifi=True, name__iexact=name).exclude(pk=current and current.pk).exists():
            errors["name"] = ["This region already has a Pocket WiFi plan with this name."]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class StaffRegionSerializer(serializers.ModelSerializer):
    plans = StaffPlanSerializer(many=True, read_only=True, source="live_plans")

    class Meta:
        model = Region
        fields = ["id", "name", "countries", "is_active", "created_at", "updated_at", "plans"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_countries(self, value):
        try:
            return normalize_countries(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.messages)

    def validate(self, attrs):
        current = self.instance
        active = attrs.get("is_active", current.is_active if current else True)
        countries = attrs.get("countries", current.countries if current else [])
        clash = overlapping_region(countries, current and current.pk) if active else None
        if clash:
            raise serializers.ValidationError({"countries": [f"{country_name(clash[0])} is already in region {clash[1].name}."]})
        return attrs


class StaffProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "product_name", "product_type", "product_thumbnail_img", "product_description", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "product_thumbnail_img", "created_at", "updated_at"]


class StaffProductViewSet(viewsets.ModelViewSet):
    permission_classes = [IsMarketingOrAdmin]
    serializer_class = StaffProductSerializer

    def get_queryset(self):
        p = self.request.query_params
        qs = Product.objects.all()
        if p.get("product_type"):
            qs = qs.filter(product_type=p["product_type"])
        if p.get("is_active") in ("true", "false"):
            qs = qs.filter(is_active=p["is_active"] == "true")
        if p.get("search"):
            qs = qs.filter(product_name__icontains=p["search"])
        return qs.order_by("product_name")

    def destroy(self, request, *args, **kwargs):
        self.get_object().soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    def thumbnail(self, request, pk=None):
        product = self.get_object()
        f = request.FILES.get("file")
        if not f:
            return Response({"file": ["No file uploaded."]}, status=400)
        if f.size > MAX_THUMBNAIL_BYTES:
            return Response({"file": ["Image must be 2 MB or smaller."]}, status=400)
        try:
            img = Image.open(f)
            img.verify()
            ext = IMAGE_EXT[img.format]
        except (UnidentifiedImageError, KeyError, OSError, SyntaxError):
            return Response({"file": ["Upload a PNG, JPEG, WEBP or GIF image."]}, status=400)
        f.seek(0)
        product.product_thumbnail_img.save(f"{uuid.uuid4()}.{ext}", f, save=True)
        return Response(self.get_serializer(self.get_queryset().get(pk=product.pk)).data)


class StaffRegionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsMarketingOrAdmin]
    serializer_class = StaffRegionSerializer

    def get_queryset(self):
        qs = Region.objects.prefetch_related(Prefetch("plans", queryset=RegionPlan.objects.all(), to_attr="live_plans"))
        if self.request.query_params.get("search"):
            qs = qs.filter(name__icontains=self.request.query_params["search"])
        return qs

    def perform_create(self, serializer):
        serializer.save().live_plans = []  # a new region has none; the prefetch above only runs on reads

    def destroy(self, request, *args, **kwargs):
        self.get_object().soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class StaffPlanViewSet(viewsets.ModelViewSet):
    permission_classes = [IsMarketingOrAdmin]
    serializer_class = StaffPlanSerializer

    def region(self):
        return get_object_or_404(Region.objects, pk=self.kwargs["region_pk"])

    def get_queryset(self):
        return RegionPlan.objects.filter(region=self.region())

    def perform_create(self, serializer):
        serializer.save(region=self.region())

    def destroy(self, request, *args, **kwargs):
        self.get_object().soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class StaffCountrySerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    region = serializers.CharField()
    is_popular = serializers.BooleanField()


class PopularChangeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=2)
    is_popular = serializers.BooleanField()

    def validate_code(self, value):
        try:
            return normalize_countries([value])[0]
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.messages)


class PopularChangesSerializer(serializers.Serializer):
    countries = PopularChangeSerializer(many=True, allow_empty=False)


class StaffCountriesView(APIView):
    """Countries on sale (those in an active region) and whether the store shows them as popular."""

    permission_classes = [IsMarketingOrAdmin]

    @extend_schema(responses=StaffCountrySerializer(many=True))
    def get(self, request):
        popular = set(PopularCountry.objects.values_list("country_code", flat=True))
        regions = {}
        for r in active_regions():
            for code in r.countries:
                regions.setdefault(code, r.name)
        rows = [{"code": c, "name": country_name(c), "region": name, "is_popular": c in popular} for c, name in regions.items()]
        return Response(sorted(rows, key=lambda r: r["name"]))

    @extend_schema(request=PopularChangesSerializer, responses=StaffCountrySerializer(many=True))
    def patch(self, request):
        """Only the countries sent change, so ones hidden by an inactive region keep their flag."""
        s = PopularChangesSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        wanted = {c["code"]: c["is_popular"] for c in s.validated_data["countries"]}
        with transaction.atomic():
            PopularCountry.objects.filter(country_code__in=[c for c, on in wanted.items() if not on]).delete()
            PopularCountry.objects.bulk_create([PopularCountry(country_code=c) for c, on in wanted.items() if on], ignore_conflicts=True)
            transaction.on_commit(signals.catalog_changed)  # once per save: bulk writes send no signals
        return self.get(request)
