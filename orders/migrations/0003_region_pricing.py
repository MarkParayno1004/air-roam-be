import django.db.models.deletion
from django.db import migrations, models


def refuse_if_data(apps, schema_editor):
    """Variants and their order lines can't be mapped to regions automatically; never drop them silently."""
    if apps.get_model("orders", "OrderLine").objects.exists() or apps.get_model("catalog", "ProductVariant").objects.exists():
        raise RuntimeError(
            "Region pricing replaces product variants. This database still has variants or order lines; "
            "convert or remove them before migrating."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0002_order_attention_note_order_needs_attention"),
        ("catalog", "0003_region_regionplan"),
    ]

    operations = [
        migrations.RunPython(refuse_if_data, migrations.RunPython.noop),
        migrations.AddField("order", "delivery_fee", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
        migrations.RemoveField("orderline", "product_variant"),
        migrations.AddField(
            "orderline",
            "product",
            models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="order_lines", to="catalog.product"),
        ),
        migrations.AddField(
            "orderline",
            "region_plan",
            models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="order_lines", to="catalog.regionplan"),
        ),
    ]
