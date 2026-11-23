from django.urls import path

from orders.staff_views import StaffOrderViewSet

urlpatterns = [
    path("orders", StaffOrderViewSet.as_view({"get": "list"})),
    path("orders/<uuid:pk>", StaffOrderViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})),
]
