from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.response import Response

from accounts.permissions import AdminWriteOtherwiseStaffRead
from bookings.models import Booking, BookingStatus
from bookings.rules import check_dates, check_destinations
from bookings.serializers import BookingDetailSerializer
from catalog.models import PricingUnit


class StaffBookingSerializer(BookingDetailSerializer):
    customer_email = serializers.EmailField(source="order_line.order.user.email", read_only=True)
    rental_days = serializers.IntegerField(source="order_line.rental_days", read_only=True)

    class Meta(BookingDetailSerializer.Meta):
        fields = BookingDetailSerializer.Meta.fields + ["customer_email", "rental_days"]


class StaffBookingInput(serializers.Serializer):
    start_at = serializers.DateTimeField(required=False)
    end_at = serializers.DateTimeField(required=False)
    booking_status = serializers.ChoiceField(choices=BookingStatus.choices, required=False)
    destination_country_codes = serializers.ListField(child=serializers.CharField(max_length=2), required=False)


class StaffBookingUpdateResponse(StaffBookingSerializer):
    rental_days_changed = serializers.BooleanField()

    class Meta(StaffBookingSerializer.Meta):
        fields = StaffBookingSerializer.Meta.fields + ["rental_days_changed"]


class StaffBookingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [AdminWriteOtherwiseStaffRead]
    serializer_class = StaffBookingSerializer

    def get_queryset(self):
        p = self.request.query_params
        qs = Booking.objects.select_related("order_line__order__user").filter(order_line__order__deleted_at__isnull=True)
        if p.get("booking_status"):
            qs = qs.filter(booking_status=p["booking_status"])
        if p.get("start_from"):
            qs = qs.filter(start_at__date__gte=p["start_from"])
        if p.get("start_to"):
            qs = qs.filter(start_at__date__lte=p["start_to"])
        if p.get("country"):
            qs = qs.filter(destination_country_codes__contains=[p["country"].strip().upper()])
        return qs

    @extend_schema(request=StaffBookingInput, responses=StaffBookingUpdateResponse)
    def partial_update(self, request, pk=None):
        """Admins may change any booking, including Pocket WiFi rental dates (travelers can't)."""
        booking = self.get_object()
        line = booking.order_line
        s = StaffBookingInput(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        start, end = d.get("start_at", booking.start_at), d.get("end_at", booking.end_at)
        days = check_dates(start, end, allow_past=True)
        booking.start_at, booking.end_at = start, end
        if "destination_country_codes" in d:
            booking.destination_country_codes = check_destinations(d["destination_country_codes"], line.countries_snapshot)
        if "booking_status" in d:
            booking.booking_status = d["booking_status"]
        booking.save()
        data = dict(self.get_serializer(booking).data)
        data["rental_days_changed"] = line.pricing_unit_snapshot == PricingUnit.PER_DAY and days != line.rental_days
        return Response(data)
