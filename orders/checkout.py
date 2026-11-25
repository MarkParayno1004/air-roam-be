from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction

from bookings.models import Booking
from bookings.rules import check_dates
from catalog.models import PricingUnit, Product, ProductType, RegionPlan, country_name
from common.errors import DomainError
from orders.models import Order, OrderLine

DELIVERY_FEE = Decimal("200.00")
DELIVERY_FEE_MAX_DAYS = 7  # total Pocket WiFi days in the order; more than this ships free


@dataclass
class CheckoutResult:
    order: Order
    price_updates: list = field(default_factory=list)
    removed_lines: list = field(default_factory=list)


def _money(d):
    return f"{d:.2f}"


def _line_name(product, code, plan):
    """Country plus plan; the product's own name is stored and shown next to it."""
    if not product:
        return ""
    place = country_name(code) if code else plan and plan.region.name  # no country = the whole region
    return f"{place} {plan.label}" if place and plan else ""


def _notice_name(product, line_name):
    return f"{product.product_name} · {line_name}" if line_name else ""


def _current_price(product, code, plan):
    """Plan price (per day for Pocket WiFi); None when it can't be sold."""
    if product is None or not product.is_active or product.deleted_at:
        return None
    if plan is None or not plan.is_active or plan.deleted_at:
        return None
    if plan.for_wifi != (product.product_type == ProductType.POCKET_WIFI):
        return None
    region = plan.region
    if not region.is_active or region.deleted_at or (code and code not in region.countries):
        return None
    return plan.price


@transaction.atomic
def create_order(user, client, lines):
    """Price every line at current region prices; report changes and unavailable items as warnings."""
    products = Product.all_objects.in_bulk([l["product_id"] for l in lines])
    plans = RegionPlan.all_objects.select_related("region").in_bulk([l["region_plan_id"] for l in lines if l.get("region_plan_id")])
    kept, updates, removed = [], [], []
    for l in lines:
        product, code = products.get(l["product_id"]), l.get("country_code", "").upper()
        wifi = product is not None and product.product_type == ProductType.POCKET_WIFI
        if wifi and not code:
            raise DomainError("country_required", "Choose a country.")
        if product and not l.get("region_plan_id"):
            raise DomainError("plan_required", "Choose a plan.")
        plan = plans.get(l.get("region_plan_id"))
        name, price = _line_name(product, code, plan), _current_price(product, code, plan)
        if price is None:
            removed.append({"name": _notice_name(product, name)})
            continue
        days = check_dates(l.get("start_at"), l.get("end_at")) if wifi else None
        kept.append((l, product, code, plan, name, price, days))
    if not kept:
        raise DomainError("nothing_to_buy", "The plans in your cart are no longer available.", status=409)

    total_days = sum(days for *_, days in kept if days)
    delivery_fee = DELIVERY_FEE if 0 < total_days <= DELIVERY_FEE_MAX_DAYS else Decimal(0)

    order = Order.objects.create(user=user, client=client, delivery_fee=delivery_fee)
    total = delivery_fee
    for l, product, code, plan, name, price, days in kept:
        if price != l["expected_unit_price"]:
            updates.append({"name": _notice_name(product, name), "old_unit_price": _money(l["expected_unit_price"]), "new_unit_price": _money(price)})
        line_total = price * l["quantity"] * (days or 1)
        ol = OrderLine.objects.create(
            order=order,
            product=product,
            region_plan=plan,
            product_name_snapshot=product.product_name,
            variant_name_snapshot=name,
            product_type_snapshot=product.product_type,
            pricing_unit_snapshot=PricingUnit.PER_DAY if days else PricingUnit.PER_PLAN,
            countries_snapshot=[code] if code else plan.region.countries,
            quantity=l["quantity"],
            unit_price=price,
            rental_days=days,
            line_total=line_total,
        )
        if days:
            Booking.objects.create(order_line=ol, start_at=l["start_at"], end_at=l["end_at"], destination_country_codes=[code])
        total += line_total
    order.total_amount = total
    order.save(update_fields=["total_amount", "updated_at"])
    return CheckoutResult(order, updates, removed)
