from django.contrib import admin

from catalog.models import Product, ProductVariant, Region, RegionPlan

admin.site.register(Product, list_display=["product_name", "product_type", "is_active", "deleted_at"])
admin.site.register(ProductVariant, list_display=["name", "countries", "price", "pricing_unit", "is_active"])
admin.site.register(Region, list_display=["name", "countries", "pocket_wifi_daily_rate", "is_active"])
admin.site.register(RegionPlan, list_display=["region", "data_mb", "validity_days", "price", "is_active"])
