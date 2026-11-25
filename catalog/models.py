from decimal import Decimal

from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator
from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.db import models
from django_countries import countries as COUNTRIES

from common.models import SoftDeleteModel


class ProductType(models.TextChoices):
    SIM = "sim", "SIM"
    ESIM = "esim", "eSIM"
    POCKET_WIFI = "pocket_wifi", "Pocket WiFi"


class VariantRegion(models.TextChoices):
    ASIA = "asia", "Asia"
    EUROPE = "europe", "Europe"
    NORTH_AMERICA = "north_america", "North America"
    SOUTH_AMERICA = "south_america", "South America"
    AFRICA = "africa", "Africa"
    OCEANIA = "oceania", "Oceania"
    MIDDLE_EAST = "middle_east", "Middle East"
    LOCAL_PH = "local_ph", "Local PH"
    GLOBAL = "global", "Global"


class PricingUnit(models.TextChoices):
    PER_PLAN = "per_plan", "Per plan"
    PER_DAY = "per_day", "Per day"


def normalize_countries(codes):
    """Uppercase, de-duplicate, sort; reject empty lists and non ISO-3166 alpha-2 codes."""
    cleaned = sorted({(c or "").strip().upper() for c in codes or []})
    if not cleaned:
        raise ValidationError("At least one country is required.")
    invalid = [c for c in cleaned if len(c) != 2 or not COUNTRIES.name(c)]
    if invalid:
        raise ValidationError(f"Unknown country code(s): {', '.join(invalid)}")
    return cleaned


def country_name(code):
    return COUNTRIES.name(code)


class Product(SoftDeleteModel):
    product_name = models.CharField(max_length=200)
    product_type = models.CharField(max_length=20, choices=ProductType.choices)
    product_thumbnail_img = models.ImageField(upload_to="thumbnails/", blank=True)
    product_description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["product_name"]

    def __str__(self):
        return self.product_name


class Region(SoftDeleteModel):
    """Staff-only price zone. Customers pick a country; its region decides the price."""

    name = models.CharField(max_length=100)
    countries = ArrayField(models.CharField(max_length=2))
    pocket_wifi_daily_rate = models.DecimalField(  # null = no Pocket WiFi here
        max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0.01"))]
    )
    is_active = models.BooleanField(default=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["name"]
        indexes = [GinIndex(fields=["countries"], name="region_countries_gin")]

    def save(self, *args, **kwargs):
        self.countries = normalize_countries(self.countries)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class RegionPlan(SoftDeleteModel):
    """A SIM/eSIM plan sold in every country of its region."""

    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="plans")
    data_mb = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])  # null = unlimited
    validity_days = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    is_active = models.BooleanField(default=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["validity_days", "price"]

    @property
    def label(self) -> str:
        data = f"{round(self.data_mb / 1024, 1):g}GB" if self.data_mb else "Unlimited"
        return f"{data} · {self.validity_days} day{'' if self.validity_days == 1 else 's'}"

    def __str__(self):
        return f"{self.region} {self.label}"


def active_regions():
    return Region.objects.filter(is_active=True).order_by("created_at")


def region_for_country(code):
    return active_regions().filter(countries__contains=[code]).first()


def overlapping_region(countries, exclude_pk=None):
    """First (country, other active region) already covering one of these countries, or None."""
    # shortcut: overlap checked in the serializer only, add a country table with a unique constraint if staff edit regions concurrently
    other = active_regions().filter(countries__overlap=countries).exclude(pk=exclude_pk).first()
    return (next(c for c in countries if c in other.countries), other) if other else None


class ProductVariant(SoftDeleteModel):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="variants")
    name = models.CharField(max_length=200)
    countries = ArrayField(models.CharField(max_length=2))
    region = models.CharField(max_length=20, choices=VariantRegion.choices)
    tag = models.CharField(max_length=50, null=True, blank=True)
    is_featured = models.BooleanField(default=False)
    data_mb = models.PositiveIntegerField(null=True, blank=True)  # null = unlimited
    validity_days = models.PositiveIntegerField(null=True, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    pricing_unit = models.CharField(max_length=10, choices=PricingUnit.choices, default=PricingUnit.PER_PLAN)
    is_active = models.BooleanField(default=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["price"]
        indexes = [GinIndex(fields=["countries"], name="variant_countries_gin")]

    def save(self, *args, **kwargs):
        self.countries = normalize_countries(self.countries)
        super().save(*args, **kwargs)

    @property
    def scope(self) -> str:
        return "multi" if len(self.countries) > 1 else "single"

    @property
    def is_sellable(self):
        p = self.product
        return self.is_active and self.deleted_at is None and p.is_active and p.deleted_at is None

    def __str__(self):
        return self.name
