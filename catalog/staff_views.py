import uuid

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from accounts.permissions import IsMarketingOrAdmin
from catalog.models import Product, Region, RegionPlan, country_name, normalize_countries, overlapping_region

MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024
IMAGE_EXT = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp", "GIF": "gif"}


class StaffPlanSerializer(serializers.ModelSerializer):
    label = serializers.ReadOnlyField()

    class Meta:
        model = RegionPlan
        fields = ["id", "label", "data_mb", "validity_days", "price", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class StaffRegionSerializer(serializers.ModelSerializer):
    plans = StaffPlanSerializer(many=True, read_only=True, source="live_plans")

    class Meta:
        model = Region
        fields = ["id", "name", "countries", "pocket_wifi_daily_rate", "is_active", "created_at", "updated_at", "plans"]
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
