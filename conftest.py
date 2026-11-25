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
def region_factory(db):
    from catalog.models import Region

    def make(**fields):
        return Region.objects.create(**{"name": "Asia 1", "countries": ["JP"], **fields})

    return make


@pytest.fixture
def plan_factory(region_factory):
    from decimal import Decimal

    from catalog.models import RegionPlan

    def make(region=None, **fields):
        return RegionPlan.objects.create(region=region or region_factory(), **{"data_mb": 5120, "validity_days": 7, "price": Decimal("399.00"), **fields})

    return make


@pytest.fixture
def wifi_plan_factory(plan_factory):
    from decimal import Decimal

    def make(region=None, **fields):
        return plan_factory(region, **{"for_wifi": True, "name": "Unlimited", "data_mb": None, "validity_days": None, "price": Decimal("100.00"), **fields})

    return make


@pytest.fixture
def product_factory(db):
    from catalog.models import Product

    def make(product_type="esim", **fields):
        return Product.objects.create(**{"product_name": f"Air Roam {product_type}", "product_type": product_type, **fields})

    return make


@pytest.fixture
def order_factory(product_factory, region_factory, plan_factory, wifi_plan_factory, user):
    """Japan order created through checkout (no Xendit call). kind: 'esim' (799) | 'wifi' (350/day)."""
    from datetime import timedelta
    from decimal import Decimal

    from django.utils import timezone

    from catalog.models import active_regions
    from orders.checkout import create_order

    def make(kind="esim", owner=None, client="web", start_in_days=3, nights=6):
        region = active_regions().filter(countries__contains=["JP"]).first() or region_factory()
        line = {"country_code": "JP", "quantity": 1}
        if kind == "wifi":
            start = timezone.now() + timedelta(days=start_in_days)
            plan = wifi_plan_factory(region=region, price=Decimal("350.00"))
            line |= {"product_id": product_factory("pocket_wifi").id, "start_at": start, "end_at": start + timedelta(days=nights)}
        else:
            plan = plan_factory(region=region, price=Decimal("799.00"))
            line |= {"product_id": product_factory("esim").id}
        line |= {"region_plan_id": plan.id, "expected_unit_price": plan.price}
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
