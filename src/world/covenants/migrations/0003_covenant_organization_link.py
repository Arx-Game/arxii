# Generated manually for Task A8 — link Covenant to Organization via OneToOne primary_key=True.
# The old auto-id pk is replaced. No existing Covenant rows exist (pre-launch), so
# no data migration is needed.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("covenants", "0002_initial"),
        ("societies", "0008_alter_organization_society"),
    ]

    operations = [
        # Drop the old auto-id primary key.
        migrations.RemoveField(
            model_name="covenant",
            name="id",
        ),
        # Add the new OneToOne FK as primary key.
        migrations.AddField(
            model_name="covenant",
            name="organization",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                primary_key=True,
                related_name="covenant",
                serialize=False,
                to="societies.organization",
            ),
        ),
    ]
