import django.core.validators
from django.db import migrations, models
from django.db.models import Min


def rates_to_plans(apps, schema_editor):
    RegionPlan = apps.get_model("catalog", "RegionPlan")
    RegionPlan.objects.bulk_create(
        RegionPlan(region=r, for_wifi=True, name="Unlimited", price=r.pocket_wifi_daily_rate)
        for r in apps.get_model("catalog", "Region").all_objects.filter(pocket_wifi_daily_rate__isnull=False)
    )


def plans_to_rates(apps, schema_editor):
    wifi = apps.get_model("catalog", "RegionPlan").all_objects.filter(for_wifi=True)
    on_sale = wifi.filter(is_active=True, deleted_at=None).order_by()
    rates = dict(on_sale.values_list("region").annotate(Min("price")))
    for region in apps.get_model("catalog", "Region").all_objects.all():
        region.pocket_wifi_daily_rate = rates.get(region.pk)
        region.save(update_fields=["pocket_wifi_daily_rate"])
    # before WiFi plans, Pocket WiFi order lines had no plan; their snapshots keep what was bought
    apps.get_model("orders", "OrderLine").objects.filter(region_plan__for_wifi=True).update(region_plan=None)
    wifi.delete()
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # run the pending FK checks so the table can be altered next


class Migration(migrations.Migration):
    dependencies = [("catalog", "0005_popularcountry")]

    operations = [
        migrations.AddField("regionplan", "for_wifi", models.BooleanField(default=False)),
        migrations.AddField("regionplan", "name", models.CharField(blank=True, default="", max_length=50)),
        migrations.AlterField(
            "regionplan",
            "validity_days",
            models.PositiveIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1)]),
        ),
        migrations.RunPython(rates_to_plans, plans_to_rates),
    ]
