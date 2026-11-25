from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0003_region_pricing")]

    operations = [
        migrations.RenameField("order", "xendit_invoice_id", "payment_session_id"),
        migrations.RenameField("order", "xendit_invoice_url", "payment_url"),
        migrations.AddField("order", "received_centavos", models.PositiveBigIntegerField(blank=True, null=True)),
    ]
