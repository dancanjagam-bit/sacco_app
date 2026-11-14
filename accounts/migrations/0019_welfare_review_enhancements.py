"""Welfare review enhancements: needs_information status, review tracking, and fund balance fields."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0018_welfare_support"),
    ]

    operations = [
        migrations.AlterField(
            model_name="welfarerequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("submitted", "Submitted"),
                    ("needs_information", "Needs additional information"),
                    ("under_review", "Under review"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                ],
                default="submitted",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="welfarerequest",
            name="review_notes",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="welfarerequest",
            name="reviewed_by",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="welfare_reviews",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="welfarerequest",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="welfarerequest",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
