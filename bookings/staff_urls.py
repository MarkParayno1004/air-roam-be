from django.urls import path

from bookings.staff_views import StaffBookingViewSet

urlpatterns = [
    path("bookings", StaffBookingViewSet.as_view({"get": "list"})),
    path("bookings/<uuid:pk>", StaffBookingViewSet.as_view({"get": "retrieve", "patch": "partial_update"})),
]
