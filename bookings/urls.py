from django.urls import path

from bookings.views import BookingViewSet, CreateBookingView

urlpatterns = [
    path("order-lines/<uuid:line_id>/booking", CreateBookingView.as_view()),
    path("bookings", BookingViewSet.as_view({"get": "list"})),
    path("bookings/<uuid:pk>", BookingViewSet.as_view({"get": "retrieve", "patch": "partial_update"})),
]
