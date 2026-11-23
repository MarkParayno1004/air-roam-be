from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from drf_spectacular.views import SpectacularAPIView

from config.api import health

TRAVELER = ["accounts.urls", "catalog.urls", "orders.urls", "bookings.urls", "payments.urls"]
STAFF = ["accounts.staff_urls", "catalog.staff_urls", "orders.staff_urls", "bookings.staff_urls"]


def build_urlpatterns():
    from django.urls import include

    patterns = [
        path("api/v1/health", health),
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    ]
    patterns += [path("api/v1/staff/", include(m)) for m in STAFF]
    patterns += [path("api/v1/", include(m)) for m in TRAVELER]
    if settings.ADMIN_ENABLED:
        patterns.append(path(settings.ADMIN_URL, admin.site.urls))
    if settings.DEBUG:
        patterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    return patterns


urlpatterns = build_urlpatterns()
