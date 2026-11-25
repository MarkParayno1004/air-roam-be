from django.urls import path

from bookings.views import BookingViewSet

urlpatterns = [
    path("bookings", BookingViewSet.as_view({"get": "list"})),
    path("bookings/<uuid:pk>", BookingViewSet.as_view({"get": "retrieve"})),
]
