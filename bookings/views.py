from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.models import Booking, BookingStatus
from bookings.rules import check_dates, check_destinations
from bookings.serializers import BookingDetailSerializer, BookingInputSerializer
from catalog.models import PricingUnit
from common.errors import DomainError
from orders.models import OrderLine

PAID_STATES = ("paid", "fulfilled")


def _require_per_plan(line):
    if line.pricing_unit_snapshot == PricingUnit.PER_DAY:
        raise DomainError("rental_dates_locked", "Rental dates can't be changed online. Contact support for changes.")


class CreateBookingView(APIView):
    @extend_schema(request=BookingInputSerializer, responses={201: BookingDetailSerializer})
    def post(self, request, line_id):
        line = get_object_or_404(
            OrderLine.objects.select_related("order"), pk=line_id, order__user=request.user, order__deleted_at__isnull=True
        )
        if line.order.order_status not in PAID_STATES:
            raise DomainError("order_not_paid", "Travel dates can be chosen once the order is paid.")
        _require_per_plan(line)
        if Booking.objects.filter(order_line=line).exists():
            raise DomainError("already_booked", "This plan already has travel dates. Edit them instead.")
        s = BookingInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        check_dates(d["start_at"], d["end_at"])
        booking = Booking.objects.create(
            order_line=line,
            start_at=d["start_at"],
            end_at=d["end_at"],
            destination_country_codes=check_destinations(d.get("destination_country_codes"), line.countries_snapshot),
            booking_status=BookingStatus.CONFIRMED,
        )
        return Response(BookingDetailSerializer(booking).data, status=status.HTTP_201_CREATED)


class BookingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = BookingDetailSerializer

    def get_queryset(self):
        return Booking.objects.select_related("order_line").filter(
            order_line__order__user=self.request.user, order_line__order__deleted_at__isnull=True
        )

    @extend_schema(request=BookingInputSerializer(partial=True), responses=BookingDetailSerializer)
    def partial_update(self, request, pk=None):
        booking = self.get_object()
        line = booking.order_line
        _require_per_plan(line)
        if booking.booking_status in (BookingStatus.CANCELLED, BookingStatus.COMPLETED) or booking.start_at <= timezone.now():
            raise DomainError("booking_locked", "This booking has started or ended and can't be changed.")
        s = BookingInputSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        start, end = d.get("start_at", booking.start_at), d.get("end_at", booking.end_at)
        check_dates(start, end)
        booking.start_at, booking.end_at = start, end
        if "destination_country_codes" in d:
            booking.destination_country_codes = check_destinations(d["destination_country_codes"], line.countries_snapshot)
        booking.save()
        return Response(BookingDetailSerializer(booking).data)
