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
    """Price zone. Customers pick a country (or a whole region for SIM/eSIM); the region decides the price."""

    name = models.CharField(max_length=100)
    countries = ArrayField(models.CharField(max_length=2))
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
    """A plan sold in every country of its region: SIM/eSIM (price and data per plan) or Pocket WiFi (price and data per day)."""

    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="plans")
    for_wifi = models.BooleanField(default=False)
    name = models.CharField(max_length=50, blank=True, default="")  # Pocket WiFi only
    data_mb = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])  # null = unlimited
    validity_days = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])  # null = Pocket WiFi
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    is_active = models.BooleanField(default=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["validity_days", "price"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(for_wifi=True, validity_days__isnull=True) | models.Q(for_wifi=False, validity_days__isnull=False),
                name="only_wifi_plans_have_no_validity",
            )
        ]

    @property
    def label(self) -> str:
        data = f"{round(self.data_mb / 1024, 2):g}GB" if self.data_mb else "Unlimited"
        if self.for_wifi:
            data += "/day" if self.data_mb else ""
            return self.name if self.name.lower() == data.lower() else f"{self.name} · {data}"
        return f"{data} · {self.validity_days} day{'' if self.validity_days == 1 else 's'}"

    def __str__(self):
        return f"{self.region} {self.label}"


class PopularCountry(models.Model):
    """Countries staff picked for the store's Popular section. Kept per country so moving regions doesn't lose it."""

    country_code = models.CharField(max_length=2, primary_key=True)

    def __str__(self):
        return self.country_code


def active_regions():
    return Region.objects.filter(is_active=True).order_by("created_at")


def overlapping_region(countries, exclude_pk=None):
    """First (country, other active region) already covering one of these countries, or None."""
    # shortcut: overlap checked in the serializer only, add a country table with a unique constraint if staff edit regions concurrently
    other = active_regions().filter(countries__overlap=countries).exclude(pk=exclude_pk).first()
    return (next(c for c in countries if c in other.countries), other) if other else None
