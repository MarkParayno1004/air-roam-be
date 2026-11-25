from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction

from bookings.models import Booking
from bookings.rules import check_dates
from catalog.models import PricingUnit, Product, ProductType, RegionPlan, country_name, region_for_country
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
    country = country_name(code)
    if not product or not country:
        return ""
    if product.product_type == ProductType.POCKET_WIFI:
        return f"{country} {ProductType.POCKET_WIFI.label}"
    return f"{country} {plan.label}" if plan else ""


def _current_price(product, code, plan):
    """Plan price, or the country's own Pocket WiFi daily rate; None when it can't be sold."""
    if product is None or not product.is_active or product.deleted_at:
        return None
    if product.product_type == ProductType.POCKET_WIFI:
        region = region_for_country(code)
        return region and region.pocket_wifi_daily_rate
    if plan is None or not plan.is_active or plan.deleted_at:
        return None
    region = plan.region
    if not region.is_active or region.deleted_at or code not in region.countries:
        return None
    return plan.price


@transaction.atomic
def create_order(user, client, lines):
    """Price every line at current region prices; report changes and unavailable items as warnings."""
    products = Product.all_objects.in_bulk([l["product_id"] for l in lines])
    plans = RegionPlan.all_objects.select_related("region").in_bulk([l["region_plan_id"] for l in lines if l.get("region_plan_id")])
    kept, updates, removed = [], [], []
    for l in lines:
        product, code = products.get(l["product_id"]), l["country_code"].upper()
        wifi = product is not None and product.product_type == ProductType.POCKET_WIFI
        if product and not wifi and not l.get("region_plan_id"):
            raise DomainError("plan_required", "Choose a plan.")
        plan = None if wifi else plans.get(l.get("region_plan_id"))
        name, price = _line_name(product, code, plan), _current_price(product, code, plan)
        if price is None:
            removed.append({"name": name})
            continue
        days = check_dates(l.get("start_at"), l.get("end_at")) if wifi else None
        kept.append((l, product, code, plan, name, price, days))
    if not kept:
        raise DomainError("nothing_to_buy", "The plans in your cart are no longer available.", status=409)

    # Every Pocket WiFi line pays the highest daily rate among the lines that are still for sale.
    daily_rate = max((price for *_, price, days in kept if days), default=None)
    total_days = sum(days for *_, days in kept if days)
    delivery_fee = DELIVERY_FEE if 0 < total_days <= DELIVERY_FEE_MAX_DAYS else Decimal(0)

    order = Order.objects.create(user=user, client=client, delivery_fee=delivery_fee)
    total = delivery_fee
    for l, product, code, plan, name, price, days in kept:
        unit_price = daily_rate if days else price
        if unit_price != l["expected_unit_price"]:
            updates.append({"name": name, "old_unit_price": _money(l["expected_unit_price"]), "new_unit_price": _money(unit_price)})
        line_total = unit_price * l["quantity"] * (days or 1)
        ol = OrderLine.objects.create(
            order=order,
            product=product,
            region_plan=plan,
            product_name_snapshot=product.product_name,
            variant_name_snapshot=name,
            product_type_snapshot=product.product_type,
            pricing_unit_snapshot=PricingUnit.PER_DAY if days else PricingUnit.PER_PLAN,
            countries_snapshot=[code],
            quantity=l["quantity"],
            unit_price=unit_price,
            rental_days=days,
            line_total=line_total,
        )
        if days:
            Booking.objects.create(order_line=ol, start_at=l["start_at"], end_at=l["end_at"], destination_country_codes=[code])
        total += line_total
    order.total_amount = total
    order.save(update_fields=["total_amount", "updated_at"])
    return CheckoutResult(order, updates, removed)
