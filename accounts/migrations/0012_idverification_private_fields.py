"""Reconcile ID verification privacy fields without duplicating existing columns.

Some local databases were modified by an earlier interrupted recovery before
the corresponding migration file was restored. This forward migration keeps
fresh installs correct and safely records the schema state on databases where
these exact columns already exist. It does not alter or delete stored values.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def ensure_private_fields(apps, schema_editor):
    verification = apps.get_model("accounts", "IDVerification")
    connection = schema_editor.connection
    table = verification._meta.db_table
    with connection.cursor() as cursor:
        existing = {
            column.name
            for column in connection.introspection.get_table_description(cursor, table)
        }

    fields = [
        (
            "data_retention_until",
            models.DateField(
                blank=True,
                help_text="Earliest date raw ID/selfie files may be deleted per retention policy.",
                null=True,
            ),
        ),
        (
            "national_id_hash",
            models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="HMAC-SHA256 of national_id; never expose or log the plaintext.",
                max_length=64,
            ),
        ),
        ("pii_last_accessed_at", models.DateTimeField(blank=True, null=True)),
        (
            "pii_last_accessed_by",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="pii_accesses",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]

    for name, field in fields:
        field.contribute_to_class(verification, name)
        if field.column not in existing:
            schema_editor.add_field(verification, field)
            existing.add(field.column)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0011_otprequest_attempt_count_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(ensure_private_fields, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="idverification",
                    name="data_retention_until",
                    field=models.DateField(
                        blank=True,
                        help_text="Earliest date raw ID/selfie files may be deleted per retention policy.",
                        null=True,
                    ),
                ),
                migrations.AddField(
                    model_name="idverification",
                    name="national_id_hash",
                    field=models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text="HMAC-SHA256 of national_id; never expose or log the plaintext.",
                        max_length=64,
                    ),
                ),
                migrations.AddField(
                    model_name="idverification",
                    name="pii_last_accessed_at",
                    field=models.DateTimeField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name="idverification",
                    name="pii_last_accessed_by",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="pii_accesses",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
