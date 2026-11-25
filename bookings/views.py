from rest_framework import mixins, viewsets

from bookings.models import Booking
from bookings.serializers import BookingDetailSerializer


class BookingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Pocket WiFi bookings are made at checkout; only staff can change them afterwards."""

    serializer_class = BookingDetailSerializer

    def get_queryset(self):
        return Booking.objects.select_related("order_line").filter(
            order_line__order__user=self.request.user, order_line__order__deleted_at__isnull=True
        )
