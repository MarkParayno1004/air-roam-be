import uuid

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from catalog.models import Product, RegionPlan
from common.models import SoftDeleteModel


class OrderStatus(models.TextChoices):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REFUNDED = "refunded"


class Client(models.TextChoices):
    WEB = "web"
    APP = "app"


class Order(SoftDeleteModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    order_status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING_PAYMENT)
    client = models.CharField(max_length=3, choices=Client.choices, default=Client.WEB)
    currency = models.CharField(max_length=3, default="PHP")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # includes delivery_fee
    delivery_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    xendit_invoice_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    xendit_invoice_url = models.URLField(max_length=500, null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    # Set when something needs a human, e.g. a payment arrived after the order was cancelled/expired.
    needs_attention = models.BooleanField(default=False)
    attention_note = models.TextField(blank=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ["-created_at"]


class OrderLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_lines")
    region_plan = models.ForeignKey(RegionPlan, on_delete=models.PROTECT, related_name="order_lines", null=True, blank=True)  # null = Pocket WiFi bought before it had plans
    product_name_snapshot = models.CharField(max_length=200)
    variant_name_snapshot = models.CharField(max_length=200)
    product_type_snapshot = models.CharField(max_length=20)
    pricing_unit_snapshot = models.CharField(max_length=10)
    countries_snapshot = ArrayField(models.CharField(max_length=2))
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    rental_days = models.PositiveIntegerField(null=True, blank=True)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
