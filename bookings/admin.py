from django.contrib import admin

from bookings.models import Booking

admin.site.register(Booking, list_display=["id", "booking_status", "start_at", "end_at", "destination_country_codes"])
