"""Date and destination rules shared by checkout (Pocket WiFi) and traveler/staff bookings."""
from django.utils import timezone

from common.errors import DomainError


def local_date(dt):
    return timezone.localtime(dt).date()


def check_dates(start_at, end_at, allow_past=False):
    """Return calendar days between start and end (>= 1)."""
    if not start_at or not end_at:
        raise DomainError("invalid_dates", "Choose a start and end date.")
    if not allow_past and local_date(start_at) < timezone.localdate():
        raise DomainError("invalid_dates", "The start date can't be in the past.")
    days = (local_date(end_at) - local_date(start_at)).days
    if end_at <= start_at or days < 1:
        raise DomainError("invalid_dates", "The end date must be after the start date.")
    return days


def check_destinations(codes, allowed):
    """Default to every allowed country; otherwise a non-empty subset of them."""
    if codes is None:
        return list(allowed)
    cleaned = sorted({c.strip().upper() for c in codes})
    if not cleaned or not set(cleaned) <= set(allowed):
        raise DomainError("invalid_destinations", "Choose at least one country covered by this plan.")
    return cleaned
