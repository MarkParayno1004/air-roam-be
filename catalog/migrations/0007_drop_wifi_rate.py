from django.db import migrations, models


class Migration(migrations.Migration):
    """Separate from 0006: Postgres can't alter a table with pending trigger events."""

    dependencies = [("catalog", "0006_wifi_plans")]

    operations = [
        migrations.RemoveField("region", "pocket_wifi_daily_rate"),
        migrations.AddConstraint(
            "regionplan",
            models.CheckConstraint(
                condition=models.Q(("for_wifi", True), ("validity_days__isnull", True)) | models.Q(("for_wifi", False), ("validity_days__isnull", False)),
                name="only_wifi_plans_have_no_validity",
            ),
        ),
    ]
