import hashlib
import hmac
import json

import pytest
import requests
from django.core.cache import cache
from rest_framework.test import APIClient

PASSWORD = "correct-horse-1"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


class FakePayMongo:
    """Stands in for `requests` inside payments.paymongo: keeps sessions, records calls, fails on demand."""

    def __init__(self):
        self.sessions, self.calls, self.down, self.fail = {}, [], False, {}

    def _answer(self, method, url, body, auth, timeout):
        self.calls.append({"method": method, "url": url, "json": body, "auth": auth, "timeout": timeout})
        path = url.removeprefix("https://api.paymongo.com/v1/checkout_sessions")
        assert path != url, f"unexpected URL {url}"
        if self.down:
            raise requests.ConnectionError("down")
        _, sid, *action = path.split("/") if path else ("", f"cs_{len(self.sessions) + 1}")
        resp = requests.Response()
        resp.status_code = self.fail.get(sid, 200)
        if resp.status_code == 200:
            if not path:
                attrs = {"checkout_url": f"https://checkout.paymongo.com/{sid}", "status": "active", "payments": [], **body["data"]["attributes"]}
                self.sessions[sid] = {"id": sid, "attributes": attrs}
            elif action == ["expire"]:
                if self.sessions[sid]["attributes"]["status"] == "active":
                    self.sessions[sid]["attributes"]["status"] = "expired"
                else:
                    resp.status_code = 400
            resp._content = json.dumps({"data": self.sessions[sid]}).encode()
        return resp

    def post(self, url, json=None, auth=None, timeout=None):
        return self._answer("POST", url, json, auth, timeout)

    def get(self, url, auth=None, timeout=None):
        return self._answer("GET", url, None, auth, timeout)

    def checkout(self, order):
        from payments import paymongo

        paymongo.create_checkout(order)
        return order.payment_session_id

    def pay(self, order, centavos=None, status="paid"):
        amount = int(order.total_amount * 100) if centavos is None else centavos
        self.sessions[order.payment_session_id]["attributes"]["payments"].append({"attributes": {"status": status, "amount": amount}})

    def hook(self, api, session_id, type="checkout_session.payment.paid", **sign):
        """Deliver a signed event whose body claims the session is paid."""
        paid = [{"attributes": {"status": "paid", "amount": 79900}}]
        body = json.dumps({"data": {"attributes": {"type": type, "livemode": False, "data": {"id": session_id, "attributes": {"payments": paid}}}}})
        return self.send(api, body, **sign)

    def send(self, api, body, secret="whsk_test", mode="te"):
        sig = hmac.new(secret.encode(), f"1700000000.{body}".encode(), hashlib.sha256).hexdigest()
        header = "t=1700000000," + (f"te={sig},li=" if mode == "te" else f"te=,li={sig}")
        return api.post("/api/v1/payments/paymongo/webhook", body, content_type="application/json", HTTP_PAYMONGO_SIGNATURE=header)


@pytest.fixture(autouse=True)
def pay_api(settings, monkeypatch):
    """Autouse: no test can reach the real PayMongo."""
    from payments import paymongo

    settings.PAYMONGO_SECRET_KEY = "sk_test_abc"
    settings.PAYMONGO_WEBHOOK_SECRET = "whsk_test"
    settings.PAYMONGO_METHODS = ["gcash", "paymaya", "qrph", "card"]
    fake = FakePayMongo()
    monkeypatch.setattr(paymongo, "requests", fake)
    return fake


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
    """Japan order created through checkout (no PayMongo call). kind: 'esim' (799) | 'wifi' (350/day)."""
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
