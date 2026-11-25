"""The only module that talks to PayMongo."""
import hashlib
import hmac

import requests
from django.conf import settings

SESSIONS_URL = "https://api.paymongo.com/v1/checkout_sessions"


def redirect_url(order):
    if order.client == "app":
        return f"{settings.APP_DEEP_LINK}?order_id={order.id}"
    return f"{settings.WEB_STORE_URL}/payment-result?order_id={order.id}"


def cancel_url(order):
    if order.client == "app":
        return redirect_url(order)
    return f"{settings.WEB_STORE_URL}/account/orders/{order.id}"


def total_centavos(order):
    return int(order.total_amount * 100)  # Decimal with two places: exact


def create_checkout(order):
    """Create a hosted checkout session for the order; store and return (session_id, checkout_url). Raises on failure."""
    name = f"Air Roam order {str(order.id)[:8]}"
    resp = requests.post(
        SESSIONS_URL,
        json={
            "data": {
                "attributes": {
                    "line_items": [{"name": name, "amount": total_centavos(order), "currency": "PHP", "quantity": 1}],
                    "payment_method_types": settings.PAYMONGO_METHODS,
                    "success_url": redirect_url(order),
                    "cancel_url": cancel_url(order),
                    "reference_number": str(order.id),
                    "description": name,
                }
            }
        },
        auth=(settings.PAYMONGO_SECRET_KEY, ""),
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    order.payment_session_id, order.payment_url = data["id"], data["attributes"]["checkout_url"]
    order.save(update_fields=["payment_session_id", "payment_url", "updated_at"])
    return order.payment_session_id, order.payment_url


def expire_checkout(order):
    """Close the hosted checkout so the order can no longer be paid. Raises on failure."""
    if not order.payment_session_id:
        return
    resp = requests.post(f"{SESSIONS_URL}/{order.payment_session_id}/expire", auth=(settings.PAYMONGO_SECRET_KEY, ""), timeout=10)
    resp.raise_for_status()


def get_session(session_id):
    """The session as PayMongo has it now. Raises on failure."""
    resp = requests.get(f"{SESSIONS_URL}/{session_id}", auth=(settings.PAYMONGO_SECRET_KEY, ""), timeout=10)
    resp.raise_for_status()
    return resp.json()["data"]


def paid_centavos(session):
    """Total received for the session; 0 when it is unpaid."""
    payments = (p["attributes"] for p in session["attributes"].get("payments") or [])
    return sum(p["amount"] for p in payments if p["status"] == "paid")


def valid_signature(raw_body, header):
    """`header` is "t=<ts>,te=<hex>,li=<hex>"; te signs test-mode events, li live ones."""
    parts = dict(p.strip().split("=", 1) for p in header.split(",") if "=" in p)
    got = parts.get("te" if settings.PAYMONGO_SECRET_KEY.startswith("sk_test_") else "li")
    secret = settings.PAYMONGO_WEBHOOK_SECRET
    if not secret or not got:
        return False
    signed = parts.get("t", "").encode() + b"." + raw_body
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(got.encode(), expected.encode())
