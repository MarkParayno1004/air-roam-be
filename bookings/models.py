import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models


class BookingStatus(models.TextChoices):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Booking(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_line = models.OneToOneField("orders.OrderLine", on_delete=models.CASCADE, related_name="booking")
    destination_country_codes = ArrayField(models.CharField(max_length=2))
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    booking_status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING)
    provider_reference = models.CharField(max_length=200, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_at"]
        constraints = [models.CheckConstraint(condition=models.Q(end_at__gt=models.F("start_at")), name="booking_end_after_start")]
