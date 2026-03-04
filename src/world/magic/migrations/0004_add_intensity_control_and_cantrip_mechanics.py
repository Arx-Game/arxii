"""Add intensity/control to Technique, mechanical fields to Cantrip.

Cantrips become technique templates that produce real Techniques at CG finalization.
Technique gains intensity (power) and control (safety/precision) stats.
The calculated_power property is removed (handled in Python, not DB).
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("magic", "0003_cantrip"),
    ]

    operations = [
        # Technique: add intensity and control
        migrations.AddField(
            model_name="technique",
            name="intensity",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Base power of the technique. Determines damage and effect strength.",
            ),
        ),
        migrations.AddField(
            model_name="technique",
            name="control",
            field=models.PositiveIntegerField(
                default=1,
                help_text=(
                    "Base safety/precision. When intensity exceeds control at runtime, "
                    "effects become unpredictable and anima cost can spike."
                ),
            ),
        ),
        # Cantrip: add mechanical fields
        migrations.AddField(
            model_name="cantrip",
            name="effect_type",
            field=models.ForeignKey(
                help_text="Mechanical effect type (Attack, Defense, Buff, etc.).",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cantrips",
                to="magic.effecttype",
            ),
            # No production data — table is empty, so no default needed at DB level
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="cantrip",
            name="style",
            field=models.ForeignKey(
                help_text="How this cantrip manifests. Filtered by character's Path at CG.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cantrips",
                to="magic.techniquestyle",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="cantrip",
            name="base_intensity",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Starting intensity for the technique created from this cantrip.",
            ),
        ),
        migrations.AddField(
            model_name="cantrip",
            name="base_control",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Starting control for the technique created from this cantrip.",
            ),
        ),
        migrations.AddField(
            model_name="cantrip",
            name="base_anima_cost",
            field=models.PositiveIntegerField(
                default=5,
                help_text="Starting anima cost for the technique created from this cantrip.",
            ),
        ),
        # Update Cantrip archetype help_text
        migrations.AlterField(
            model_name="cantrip",
            name="archetype",
            field=models.CharField(
                choices=[
                    ("attack", "Attack"),
                    ("defense", "Defense"),
                    ("buff", "Buff"),
                    ("debuff", "Debuff"),
                    ("utility", "Utility"),
                ],
                help_text="Player-facing category for CG grouping: attack, defense, buff, debuff, utility.",
                max_length=20,
            ),
        ),
    ]
