# Generated for FK target update: mechanics.PrerequisiteType → mechanics.Prerequisite

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("magic", "0003_resonance_properties"),
        ("mechanics", "0002_rename_prerequisitetype_prerequisite"),
    ]

    operations = [
        migrations.AlterField(
            model_name="techniquecapabilitygrant",
            name="prerequisite",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Source-specific prerequisite, checked in addition to Capability-level ones."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="technique_grants",
                to="mechanics.prerequisite",
            ),
        ),
    ]
