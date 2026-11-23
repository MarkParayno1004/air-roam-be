from django.contrib import admin

from catalog.models import Product, ProductVariant

admin.site.register(Product, list_display=["product_name", "product_type", "is_active", "deleted_at"])
admin.site.register(ProductVariant, list_display=["name", "countries", "price", "pricing_unit", "is_active"])
