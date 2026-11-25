from django.contrib import admin


def test_models_registered_for_developer_admin():
    from accounts.models import User
    from bookings.models import Booking
    from catalog.models import Product, ProductVariant, Region, RegionPlan
    from orders.models import Order, OrderLine

    for model in (User, Product, ProductVariant, Region, RegionPlan, Order, OrderLine, Booking):
        assert admin.site.is_registered(model), model.__name__


def test_admin_only_for_superusers(db):
    from accounts.models import User

    staff = User(email="m@x.com", permissions=["admin"])
    assert not staff.is_staff  # dashboard admins are not Django-admin users
    assert User(email="dev@x.com", is_superuser=True).is_staff
