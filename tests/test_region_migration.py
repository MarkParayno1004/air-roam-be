import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

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
