"""Demo catalog: products, regions and region plans. Safe to run repeatedly (matches by name)."""
from decimal import Decimal

from django.core.management.base import BaseCommand

from catalog.models import Product, Region, RegionPlan

PRODUCTS = [
    ("Air Roam eSIM", "esim", "Instant eSIM data. Install before you fly and switch on when you land."),
    ("Air Roam SIM", "sim", "Physical SIM card delivered to your address in the Philippines."),
    ("Air Roam Pocket WiFi", "pocket_wifi", "Rent a pocket WiFi device and share fast data with up to 5 devices."),
]
REGIONS = [
    ("Asia 1", ["JP", "KR", "SG", "TH", "MY", "VN", "HK", "TW"], "100"),
    ("North America", ["US", "CA"], "50"),
    ("Europe", ["FR", "DE", "IT", "ES", "NL", "CH", "PT", "BE", "AT", "GR"], "10"),
]
PLANS = [(5, 7, "399"), (10, 14, "699"), (14, 30, "999"), (30, 3, "499")]  # GB, days, PHP


class Command(BaseCommand):
    help = "Create or update the demo catalog."

    def handle(self, *args, **options):
        for name, ptype, desc in PRODUCTS:
            Product.objects.update_or_create(product_name=name, defaults={"product_type": ptype, "product_description": desc})
        for name, countries, rate in REGIONS:
            region, _ = Region.objects.update_or_create(name=name, defaults={"countries": countries, "pocket_wifi_daily_rate": Decimal(rate)})
            for gb, days, price in PLANS:
                RegionPlan.objects.update_or_create(region=region, data_mb=gb * 1024, validity_days=days, defaults={"price": Decimal(price)})
        self.stdout.write(self.style.SUCCESS(f"Demo catalog ready: {Region.objects.count()} regions, {RegionPlan.objects.count()} plans"))
