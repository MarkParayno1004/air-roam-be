from django.urls import path
from rest_framework.routers import SimpleRouter

from catalog import staff_views

router = SimpleRouter(trailing_slash=False)
router.register("products", staff_views.StaffProductViewSet, basename="staff-products")
router.register("regions", staff_views.StaffRegionViewSet, basename="staff-regions")

plans = staff_views.StaffPlanViewSet
urlpatterns = router.urls + [
    path("regions/<uuid:region_pk>/plans", plans.as_view({"get": "list", "post": "create"})),
    path(
        "regions/<uuid:region_pk>/plans/<uuid:pk>",
        plans.as_view({"get": "retrieve", "patch": "partial_update", "put": "update", "delete": "destroy"}),
    ),
]
