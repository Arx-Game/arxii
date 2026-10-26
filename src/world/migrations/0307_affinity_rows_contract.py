"""Contract step of the row-keyed affinity refactor (#4681; expand 0302, backfill 0303).

Schema only. ADR-0237 disposition per removed column:

- ``ResonanceConversion.target_affinity``, ``AuraAffinityThreshold.affinity``,
  ``FallRedemptionRecord.from_affinity/to_affinity``, ``CombatOpponent.affinity`` and the
  covenant situation ``affinity`` (three tables): RESTRUCTURED. Migration 0303 copied every
  value into the ``*_ref`` FK; the FK then takes the old name here by ``RenameField``.
- ``FallRedemptionConfig`` six ``*_to_*_multiplier`` and ``CorruptionConfig`` three affinity
  coefficients: CONSTANTS, written by 0303 onto ``AffinityInteraction`` and
  ``Affinity.corruption_coefficient``.
- ``CharacterAura.celestial/primal/abyssal``: copied to ``CharacterAuraShare`` rows by 0303
  (empty in production).
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0306_affinity_rows_restore_old_columns"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auraaffinitythreshold",
            name="affinity",
            field=models.CharField(
                default="",
                max_length=16,
                choices=[("celestial", "Celestial"), ("primal", "Primal"), ("abyssal", "Abyssal")],
            ),
        ),
        migrations.AlterField(
            model_name="resonanceconversion",
            name="target_affinity",
            field=models.CharField(
                default="",
                max_length=16,
                choices=[("celestial", "Celestial"), ("primal", "Primal"), ("abyssal", "Abyssal")],
            ),
        ),
        migrations.AlterField(
            model_name="fallredemptionrecord",
            name="from_affinity",
            field=models.CharField(
                default="",
                max_length=16,
                choices=[("celestial", "Celestial"), ("primal", "Primal"), ("abyssal", "Abyssal")],
            ),
        ),
        migrations.AlterField(
            model_name="fallredemptionrecord",
            name="to_affinity",
            field=models.CharField(
                default="",
                max_length=16,
                choices=[("celestial", "Celestial"), ("primal", "Primal"), ("abyssal", "Abyssal")],
            ),
        ),
        migrations.RemoveField(model_name="characteraura", name="celestial"),
        migrations.RemoveField(model_name="characteraura", name="primal"),
        migrations.RemoveField(model_name="characteraura", name="abyssal"),
        migrations.RemoveField(
            model_name="fallredemptionconfig", name="celestial_to_primal_multiplier"
        ),
        migrations.RemoveField(
            model_name="fallredemptionconfig", name="celestial_to_abyssal_multiplier"
        ),
        migrations.RemoveField(
            model_name="fallredemptionconfig", name="primal_to_abyssal_multiplier"
        ),
        migrations.RemoveField(
            model_name="fallredemptionconfig", name="abyssal_to_primal_multiplier"
        ),
        migrations.RemoveField(
            model_name="fallredemptionconfig", name="primal_to_celestial_multiplier"
        ),
        migrations.RemoveField(
            model_name="fallredemptionconfig", name="abyssal_to_celestial_multiplier"
        ),
        migrations.RemoveField(model_name="corruptionconfig", name="celestial_coefficient"),
        migrations.RemoveField(model_name="corruptionconfig", name="primal_coefficient"),
        migrations.RemoveField(model_name="corruptionconfig", name="abyssal_coefficient"),
        migrations.RemoveField(model_name="combatopponent", name="affinity"),
        migrations.RemoveField(model_name="auraaffinitythreshold", name="affinity"),
        migrations.RemoveField(model_name="resonanceconversion", name="target_affinity"),
        migrations.RemoveField(model_name="fallredemptionrecord", name="from_affinity"),
        migrations.RemoveField(model_name="fallredemptionrecord", name="to_affinity"),
        migrations.RemoveField(model_name="vowaddedeffect", name="affinity"),
        migrations.RemoveField(model_name="vowsituationalperkrung", name="affinity"),
        migrations.RemoveField(model_name="vowsituationalperksituation", name="affinity"),
        migrations.RenameField(
            model_name="combatopponent", old_name="affinity_ref", new_name="affinity"
        ),
        migrations.RenameField(
            model_name="auraaffinitythreshold", old_name="affinity_ref", new_name="affinity"
        ),
        migrations.RenameField(
            model_name="resonanceconversion",
            old_name="target_affinity_ref",
            new_name="target_affinity",
        ),
        migrations.RenameField(
            model_name="fallredemptionrecord",
            old_name="from_affinity_ref",
            new_name="from_affinity",
        ),
        migrations.RenameField(
            model_name="fallredemptionrecord", old_name="to_affinity_ref", new_name="to_affinity"
        ),
        migrations.RenameField(
            model_name="vowaddedeffect", old_name="affinity_ref", new_name="affinity"
        ),
        migrations.RenameField(
            model_name="vowsituationalperkrung", old_name="affinity_ref", new_name="affinity"
        ),
        migrations.RenameField(
            model_name="vowsituationalperksituation", old_name="affinity_ref", new_name="affinity"
        ),
        migrations.AlterField(
            model_name="auraaffinitythreshold",
            name="affinity",
            field=models.ForeignKey(
                help_text="The affinity whose share this threshold watches.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="arxii.affinity",
            ),
        ),
        migrations.AlterField(
            model_name="resonanceconversion",
            name="target_affinity",
            field=models.ForeignKey(
                help_text="The destination affinity for this conversion path.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="arxii.affinity",
            ),
        ),
        migrations.AlterField(
            model_name="fallredemptionrecord",
            name="from_affinity",
            field=models.ForeignKey(
                help_text="The affinity converted away from.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="arxii.affinity",
            ),
        ),
        migrations.AlterField(
            model_name="fallredemptionrecord",
            name="to_affinity",
            field=models.ForeignKey(
                help_text="The affinity converted into.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="arxii.affinity",
            ),
        ),
        migrations.AlterField(
            model_name="combatopponent",
            name="affinity",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Authored magical affinity for non-persona NPCs (generic/ephemeral "
                    "opponents carry no CharacterAura row to infer from). Null = "
                    "untyped/unauthored: the ATTACKER_AFFINITY situational-perk evaluator "
                    "(world.covenants.perks.evaluators) falls back to a reachable "
                    "ObjectDB's aura when this is null."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="arxii.affinity",
            ),
        ),
        migrations.AlterField(
            model_name="vowaddedeffect",
            name="affinity",
            field=models.ForeignKey(
                blank=True,
                help_text="Affinity axis for attacker typing (ATTACKER_AFFINITY).",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="arxii.affinity",
            ),
        ),
        migrations.AlterField(
            model_name="vowsituationalperkrung",
            name="affinity",
            field=models.ForeignKey(
                blank=True,
                help_text="Affinity axis for attacker typing (ATTACKER_AFFINITY).",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="arxii.affinity",
            ),
        ),
        migrations.AlterField(
            model_name="vowsituationalperksituation",
            name="affinity",
            field=models.ForeignKey(
                blank=True,
                help_text="Affinity axis for attacker typing (ATTACKER_AFFINITY).",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="arxii.affinity",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="resonanceconversion",
            unique_together={("source_resonance", "target_affinity")},
        ),
        migrations.AlterUniqueTogether(
            name="auraaffinitythreshold",
            unique_together={("affinity", "threshold_percent")},
        ),
        migrations.AddConstraint(
            model_name="affinityinteraction",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        ("conversion_multiplier__isnull", False),
                        models.Q(("conversion_type", ""), _negated=True),
                    )
                    | models.Q(("conversion_multiplier__isnull", True), ("conversion_type", ""))
                ),
                name="affinity_interaction_conversion_pair_complete",
            ),
        ),
        migrations.AlterField(
            model_name="compromiseacttype",
            name="is_cruelty",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Staff-authored: True for an act that is cruel. It separates acts the "
                    "resonance's affinity cannot (two Abyssal acts need not both be cruel), "
                    "so it is not derived from target_resonance.affinity."
                ),
            ),
        ),
    ]
