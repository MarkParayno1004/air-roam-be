from django.contrib import admin

from orders.models import Order, OrderLine

admin.site.register(Order, list_display=["id", "user", "order_status", "total_amount", "created_at"])
admin.site.register(OrderLine, list_display=["id", "order", "variant_name_snapshot", "line_total"])
