from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

OLD = [("catalog", "0003_region_regionplan"), ("orders", "0002_order_attention_note_order_needs_attention")]


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    return MigrationExecutor(connection).loader.project_state(targets).apps


@pytest.mark.django_db(transaction=True)
def test_region_migration_refuses_to_drop_existing_variants():
    latest = MigrationExecutor(connection).loader.graph.leaf_nodes()
    apps = _migrate(OLD)
    try:
        product = apps.get_model("catalog", "Product").objects.create(product_name="Old", product_type="esim")
        variants = apps.get_model("catalog", "ProductVariant").objects
        variants.create(product=product, name="Old plan", countries=["JP"], region="asia", price="1.00")
        with pytest.raises(RuntimeError, match="Region pricing replaces product variants"):
            _migrate(latest)
        assert variants.count() == 1
    finally:
        variants.all().delete()
        product.delete()
        _migrate(latest)


@pytest.mark.django_db(transaction=True)
def test_wifi_rate_becomes_an_unlimited_plan_and_back():
    latest = MigrationExecutor(connection).loader.graph.leaf_nodes()
    before = [("catalog", "0005_popularcountry")] + [n for n in latest if n[0] != "catalog"]
    apps = _migrate(before)
    try:
        regions = apps.get_model("catalog", "Region").all_objects
        asia = regions.create(name="Asia", countries=["JP"], pocket_wifi_daily_rate="350.00")
        gone = regions.create(name="Gone", countries=["US"], pocket_wifi_daily_rate="50.00", deleted_at=timezone.now())
        none = regions.create(name="None", countries=["FR"])
        sim = apps.get_model("catalog", "RegionPlan").objects.create(region=asia, data_mb=5120, validity_days=7, price="399.00")

        apps = _migrate(latest)
        plans = apps.get_model("catalog", "RegionPlan").all_objects
        copied = plans.filter(for_wifi=True).order_by("-price").values_list("region_id", "name", "data_mb", "validity_days", "price", "is_active", "deleted_at")
        assert list(copied) == [(r.pk, "Unlimited", None, None, Decimal(p), True, None) for r, p in ((asia, 350), (gone, 50))]
        kept = plans.get(pk=sim.pk)
        assert (kept.for_wifi, kept.name, kept.validity_days) == (False, "", 7)

        wifi = {"region_id": asia.pk, "for_wifi": True}
        regular = plans.create(name="Regular", data_mb=1024, price="200.00", **wifi)
        plans.create(name="Off", price="2.00", is_active=False, **wifi)
        plans.create(name="Gone", price="1.00", deleted_at=timezone.now(), **wifi)
        user = apps.get_model("accounts", "User").objects.create(email="m@example.com")
        product = apps.get_model("catalog", "Product").objects.create(product_name="WiFi", product_type="pocket_wifi")
        order = apps.get_model("orders", "Order").objects.create(user=user)
        line = order.lines.create(
            product=product, region_plan=regular, product_name_snapshot="WiFi", variant_name_snapshot="Japan Regular · 1GB/day", product_type_snapshot="pocket_wifi",
            pricing_unit_snapshot="per_day", countries_snapshot=["JP"], quantity=1, unit_price="200.00", rental_days=2, line_total="400.00",
        )

        apps = _migrate(before)
        rates = dict(apps.get_model("catalog", "Region").all_objects.values_list("pk", "pocket_wifi_daily_rate"))
        assert rates == {asia.pk: Decimal("200.00"), gone.pk: Decimal("50.00"), none.pk: None}
        assert [p.pk for p in apps.get_model("catalog", "RegionPlan").all_objects.all()] == [sim.pk]
        assert apps.get_model("orders", "OrderLine").objects.get(pk=line.pk).region_plan_id is None
    finally:
        _migrate(latest)
