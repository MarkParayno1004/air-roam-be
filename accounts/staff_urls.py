from django.urls import path
from rest_framework.routers import SimpleRouter

from accounts import staff_views

router = SimpleRouter(trailing_slash=False)
router.register("users", staff_views.StaffUserViewSet, basename="staff-users")

urlpatterns = [
    path("auth/login", staff_views.StaffLoginView.as_view()),
    path("auth/refresh", staff_views.StaffRefreshView.as_view()),
    path("auth/logout", staff_views.StaffLogoutView.as_view()),
] + router.urls
