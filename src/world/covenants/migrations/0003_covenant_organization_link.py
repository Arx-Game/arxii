# Generated manually for Task A8 — link Covenant to Organization via OneToOne.
# REVISED: Originally used primary_key=True on the OneToOne, which broke view-layer
# tests (CovenantSerializer.fields=["id",...] and other pk-using code). Switched to
# a plain OneToOne; Covenant keeps its own auto-id pk. Less aggressive, no
# downstream breakage. No existing Covenant rows (pre-launch), no data migration.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("covenants", "0002_initial"),
        ("societies", "0008_alter_organization_society"),
    ]

    operations = [
        migrations.AddField(
            model_name="covenant",
            name="organization",
            field=models.OneToOneField(
                null=True,  # nullable temporarily — auto-populated by Covenant.save()
                on_delete=django.db.models.deletion.CASCADE,
                related_name="covenant",
                to="societies.organization",
            ),
        ),
    ]
