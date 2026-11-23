"""The only module that talks to Xendit."""
import requests
from django.conf import settings

INVOICE_URL = "https://api.xendit.co/v2/invoices"


def redirect_url(order):
    if order.client == "app":
        return f"{settings.APP_DEEP_LINK}?order_id={order.id}"
    return f"{settings.WEB_STORE_URL}/payment-result?order_id={order.id}"


def expire_invoice(order):
    """Close the hosted invoice so a cancelled order can no longer be paid. Raises on failure."""
    if not order.xendit_invoice_id:
        return
    resp = requests.post(
        f"https://api.xendit.co/invoices/{order.xendit_invoice_id}/expire!",
        auth=(settings.XENDIT_SECRET_KEY, ""),
        timeout=10,
    )
    resp.raise_for_status()


def create_invoice(order):
    """Create a hosted invoice for the order; store and return (invoice_id, invoice_url). Raises on failure."""
    back = redirect_url(order)
    resp = requests.post(
        INVOICE_URL,
        json={
            "external_id": str(order.id),
            "amount": float(order.total_amount),
            "currency": "PHP",
            "description": f"Air Roam order {str(order.id)[:8]}",
            "success_redirect_url": back,
            "failure_redirect_url": back,
        },
        auth=(settings.XENDIT_SECRET_KEY, ""),
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    order.xendit_invoice_id, order.xendit_invoice_url = data["id"], data["invoice_url"]
    order.save(update_fields=["xendit_invoice_id", "xendit_invoice_url", "updated_at"])
    return order.xendit_invoice_id, order.xendit_invoice_url
