from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0020_transportpayment_received_amount_and_more")]

    operations = [
        migrations.AddField(
            model_name="transportpayment",
            name="requires_signed_callback",
            field=models.BooleanField(default=False),
        ),
    ]
