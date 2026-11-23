import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

PASSWORD = "correct-horse-1"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def api_enforce_csrf():
    return APIClient(enforce_csrf_checks=True)


def _make_user(email, permissions=None):
    from accounts.models import User

    return User.objects.create_user(email, PASSWORD, first_name="Alex", last_name="Santos", permissions=permissions or [])


@pytest.fixture
def user(db):
    return _make_user("traveler@example.com")


@pytest.fixture
def other_user(db):
    return _make_user("other@example.com")


@pytest.fixture
def admin_user(db):
    return _make_user("admin@example.com", ["admin"])


@pytest.fixture
def marketing_user(db):
    return _make_user("marketing@example.com", ["marketing"])


@pytest.fixture
def variant_factory(db):
    from decimal import Decimal

    from catalog.models import Product, ProductVariant

    def make(product=None, product_type="esim", product_active=True, **fields):
        if product is None:
            product = Product.objects.create(product_name=fields.pop("product_name", "Air Roam eSIM"), product_type=product_type, is_active=product_active)
        defaults = dict(name="Japan 10GB 7 days", countries=["JP"], region="asia", price=Decimal("799.00"), pricing_unit="per_plan", validity_days=7)
        defaults.update(fields)
        return ProductVariant.objects.create(product=product, **defaults)

    return make


@pytest.fixture
def order_factory(variant_factory, user):
    """Order created through checkout (no Xendit call). kind: 'esim' | 'wifi'."""
    from datetime import timedelta
    from decimal import Decimal

    from django.utils import timezone

    from orders.checkout import create_order

    def make(kind="esim", owner=None, client="web", start_in_days=3, nights=6):
        if kind == "wifi":
            v = variant_factory(product_type="pocket_wifi", name="Japan Pocket WiFi", price=Decimal("350.00"), pricing_unit="per_day", validity_days=None)
            start = timezone.now() + timedelta(days=start_in_days)
            line = {"variant_id": v.id, "quantity": 1, "expected_unit_price": v.price, "start_at": start, "end_at": start + timedelta(days=nights)}
        else:
            v = variant_factory()
            line = {"variant_id": v.id, "quantity": 1, "expected_unit_price": v.price}
        return create_order(owner or user, client, [line]).order

    return make


def _authed(u):
    from rest_framework_simplejwt.tokens import RefreshToken

    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(u).access_token}")
    return c


@pytest.fixture
def auth_api(user):
    return _authed(user)


@pytest.fixture
def other_api(other_user):
    return _authed(other_user)


@pytest.fixture
def admin_api(admin_user):
    return _authed(admin_user)


@pytest.fixture
def marketing_api(marketing_user):
    return _authed(marketing_user)
