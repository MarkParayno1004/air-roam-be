"""Demo catalog matching the web store design screens. Safe to run repeatedly (matches by name)."""
from decimal import Decimal

from django.core.management.base import BaseCommand

from catalog.models import Product, ProductVariant

ASIA8 = ["JP", "KR", "SG", "TH", "MY", "VN", "HK", "TW"]
EU = ["FR", "DE", "IT", "ES", "NL", "CH", "PT", "BE", "AT", "GR"]
GLOBAL = ["JP", "US", "FR", "AU", "SG", "AE", "GB", "KR", "TH", "CA"]

CATALOG = {
    ("Air Roam eSIM", "esim", "Instant eSIM data. Install before you fly and switch on when you land."): [
        ("Japan 3GB · 5 days", ["JP"], "asia", "449", 3072, 5, None, False),
        ("Japan 10GB · 7 days", ["JP"], "asia", "799", 10240, 7, "Best value", True),
        ("Japan Unlimited · 15 days", ["JP"], "asia", "1499", None, 15, None, False),
        ("South Korea 5GB · 7 days", ["KR"], "asia", "399", 5120, 7, None, True),
        ("Singapore 3GB · 5 days", ["SG"], "asia", "299", 3072, 5, None, True),
        ("Thailand 5GB · 8 days", ["TH"], "asia", "279", 5120, 8, None, True),
        ("United States 10GB · 15 days", ["US"], "north_america", "899", 10240, 15, None, True),
        ("France 10GB · 15 days", ["FR"], "europe", "799", 10240, 15, None, True),
        ("Australia 10GB · 15 days", ["AU"], "oceania", "699", 10240, 15, None, True),
        ("Asia 8 countries · 10GB · 15 days", ASIA8, "asia", "1299", 10240, 15, "Best value", False),
        ("ASEAN 6 countries · 5GB · 10 days", ["SG", "TH", "MY", "VN", "ID", "KH"], "asia", "799", 5120, 10, None, False),
        ("Europe 10 countries · 20GB · 30 days", EU, "europe", "2499", 20480, 30, None, False),
        ("Global 10 countries · 10GB · 30 days", GLOBAL, "global", "2999", 10240, 30, None, False),
    ],
    ("Air Roam SIM", "sim", "Physical SIM card delivered to your address in the Philippines."): [
        ("Japan SIM 20GB · 15 days", ["JP"], "asia", "999", 20480, 15, None, False),
        ("Philippines SIM 10GB · 30 days", ["PH"], "local_ph", "199", 10240, 30, None, True),
    ],
    ("Air Roam Pocket WiFi", "pocket_wifi", "Rent a pocket WiFi device and share fast data with up to 5 devices."): [
        ("Japan Pocket WiFi Unlimited", ["JP"], "asia", "350", None, None, "Popular", False),
        ("Japan Pocket WiFi 50GB", ["JP"], "asia", "250", 51200, None, None, False),
        ("Asia Pocket WiFi · 5 countries", ["JP", "KR", "SG", "TH", "HK"], "asia", "450", None, None, None, False),
        ("Europe Pocket WiFi · 10 countries", EU, "europe", "550", None, None, None, False),
    ],
}


class Command(BaseCommand):
    help = "Create or update the demo catalog."

    def handle(self, *args, **options):
        for (pname, ptype, desc), variants in CATALOG.items():
            product, _ = Product.objects.update_or_create(product_name=pname, defaults={"product_type": ptype, "product_description": desc})
            for name, countries, region, price, data_mb, validity, tag, featured in variants:
                ProductVariant.objects.update_or_create(
                    product=product,
                    name=name,
                    defaults=dict(
                        countries=countries, region=region, price=Decimal(price), data_mb=data_mb, validity_days=validity, tag=tag,
                        is_featured=featured, pricing_unit="per_day" if ptype == "pocket_wifi" else "per_plan",
                    ),
                )
        self.stdout.write(self.style.SUCCESS(f"Demo catalog ready: {ProductVariant.objects.count()} plans"))
