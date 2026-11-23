from rest_framework.routers import SimpleRouter

from orders.views import OrderViewSet

router = SimpleRouter(trailing_slash=False)
router.register("orders", OrderViewSet, basename="orders")
urlpatterns = router.urls
