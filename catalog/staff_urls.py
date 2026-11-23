from django.urls import path
from rest_framework.routers import SimpleRouter

from catalog import staff_views

router = SimpleRouter(trailing_slash=False)
router.register("products", staff_views.StaffProductViewSet, basename="staff-products")

variants = staff_views.StaffVariantViewSet
urlpatterns = router.urls + [
    path("products/<uuid:product_pk>/variants", variants.as_view({"get": "list", "post": "create"})),
    path(
        "products/<uuid:product_pk>/variants/<uuid:pk>",
        variants.as_view({"get": "retrieve", "patch": "partial_update", "put": "update", "delete": "destroy"}),
    ),
]
