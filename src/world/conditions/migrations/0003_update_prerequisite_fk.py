# Generated for FK target update: mechanics.PrerequisiteType → mechanics.Prerequisite

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("conditions", "0002_initial"),
        ("mechanics", "0002_rename_prerequisitetype_prerequisite"),
    ]

    operations = [
        migrations.AlterField(
            model_name="capabilitytype",
            name="prerequisite",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Capability-level prerequisite checked for ALL sources of this Capability."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="capability_types",
                to="mechanics.prerequisite",
            ),
        ),
    ]
