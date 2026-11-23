from dataclasses import dataclass, field

from django.db import transaction

from bookings.models import Booking
from bookings.rules import check_dates, check_destinations
from catalog.models import PricingUnit, ProductVariant
from common.errors import DomainError
from orders.models import Order, OrderLine


@dataclass
class CheckoutResult:
    order: Order
    price_updates: list = field(default_factory=list)
    removed_lines: list = field(default_factory=list)


def _money(d):
    return f"{d:.2f}"


@transaction.atomic
def create_order(user, client, lines):
    """Price every line at the current price; report changes and unavailable plans as warnings."""
    variants = ProductVariant.all_objects.select_related("product").in_bulk([l["variant_id"] for l in lines])
    kept, updates, removed = [], [], []
    for l in lines:
        v = variants.get(l["variant_id"])
        if v is None or not v.is_sellable:
            removed.append({"variant_id": str(l["variant_id"]), "name": v.name if v else ""})
            continue
        if v.price != l["expected_unit_price"]:
            updates.append({"variant_id": str(v.id), "name": v.name, "old_unit_price": _money(l["expected_unit_price"]), "new_unit_price": _money(v.price)})
        kept.append((l, v))
    if not kept:
        raise DomainError("nothing_to_buy", "The plans in your cart are no longer available.", status=409)

    order = Order.objects.create(user=user, client=client)
    total = 0
    for l, v in kept:
        rental_days, booking = None, None
        line_total = v.price * l["quantity"]
        if v.pricing_unit == PricingUnit.PER_DAY:
            rental_days = check_dates(l.get("start_at"), l.get("end_at"))
            destinations = check_destinations(l.get("destination_country_codes"), v.countries)
            line_total *= rental_days
            booking = {"start_at": l["start_at"], "end_at": l["end_at"], "destination_country_codes": destinations}
        ol = OrderLine.objects.create(
            order=order,
            product_variant=v,
            product_name_snapshot=v.product.product_name,
            variant_name_snapshot=v.name,
            product_type_snapshot=v.product.product_type,
            pricing_unit_snapshot=v.pricing_unit,
            countries_snapshot=v.countries,
            quantity=l["quantity"],
            unit_price=v.price,
            rental_days=rental_days,
            line_total=line_total,
        )
        if booking:
            Booking.objects.create(order_line=ol, **booking)
        total += line_total
    order.total_amount = total
    order.save(update_fields=["total_amount", "updated_at"])
    return CheckoutResult(order, updates, removed)
