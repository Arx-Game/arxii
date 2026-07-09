# Generated for generalized crossing catalog (#1990).
# Replaces the original 0093 (TraitCrossingOption etc.) with the generalized
# CrossingOption/CrossingChoice/PendingCrossingOffer schema. Pre-launch — no
# data migration needed.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("achievements", "0004_rewarddefinition_modifier_target_and_more"),
        ("codex", "0004_alter_codexclue_unique_together_and_more"),
        ("conditions", "0014_alter_conditiondamageovertime_tick_timing"),
        ("magic", "0092_combo_discovery_source"),
    ]

    operations = [
        migrations.CreateModel(
            name="CrossingOption",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "target_kind",
                    models.CharField(
                        choices=[
                            ("TRAIT", "Trait"),
                            ("TECHNIQUE", "Technique"),
                            ("FACET", "Facet"),
                            ("RELATIONSHIP_TRACK", "Relationship Track"),
                            ("RELATIONSHIP_CAPSTONE", "Relationship Capstone"),
                            ("COVENANT_ROLE", "Covenant Role"),
                            ("MANTLE", "Mantle"),
                            ("SANCTUM", "Sanctum"),
                            ("GIFT", "Gift"),
                            ("ORGANIZATION", "Organization"),
                        ],
                        help_text="Which thread kind this option applies to.",
                        max_length=32,
                    ),
                ),
                (
                    "crossing_level",
                    models.PositiveSmallIntegerField(
                        help_text="PathStage crossing level (3, 6, 11, 16, 21)."
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="The buff's identity (e.g., 'Smirk of the Spidery Seductress').",
                        max_length=120,
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Staff-authored flavor, examinable by other players.",
                    ),
                ),
                (
                    "is_default",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "When a thread skips this crossing (multi-crossing imbue), "
                            "this option is picked automatically. One per "
                            "(target_kind, resonance, crossing_level)."
                        ),
                    ),
                ),
                (
                    "codex_entry",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="crossing_options",
                        to="codex.codexentry",
                    ),
                ),
                (
                    "condition_template",
                    models.ForeignKey(
                        help_text=(
                            "The buff being chosen. Its ConditionModifierEffect rows define "
                            "the stat/check modifiers. Crossing buffs should only reference "
                            "templates carrying ConditionModifierEffect rows."
                        ),
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="crossing_options",
                        to="conditions.conditiontemplate",
                    ),
                ),
                (
                    "discovery_achievement",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="crossing_options",
                        to="achievements.achievement",
                    ),
                ),
                (
                    "resonance",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="crossing_options",
                        to="magic.resonance",
                    ),
                ),
            ],
            options={
                "ordering": ["target_kind", "resonance", "crossing_level", "id"],
                "unique_together": {("target_kind", "resonance", "crossing_level", "name")},
            },
        ),
        migrations.CreateModel(
            name="CrossingChoice",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "crossing_level",
                    models.PositiveSmallIntegerField(
                        help_text="PathStage crossing level (3, 6, 11, 16, 21)."
                    ),
                ),
                ("chosen_at", models.DateTimeField(auto_now_add=True)),
                (
                    "thread",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="crossing_choices",
                        to="magic.thread",
                    ),
                ),
                (
                    "option",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="choices",
                        to="magic.crossingoption",
                    ),
                ),
            ],
            options={
                "ordering": ["-chosen_at"],
            },
        ),
        migrations.CreateModel(
            name="PendingCrossingOffer",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "crossing_level",
                    models.PositiveSmallIntegerField(
                        help_text="PathStage crossing level (3, 6, 11, 16, 21)."
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "thread",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pending_crossing_offers",
                        to="magic.thread",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("thread",), name="one_pending_crossing_per_thread"
                    )
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="crossingoption",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_default", True)),
                fields=("target_kind", "resonance", "crossing_level"),
                name="one_default_crossing_option",
            ),
        ),
        migrations.AddConstraint(
            model_name="crossingchoice",
            constraint=models.UniqueConstraint(
                fields=("thread", "crossing_level"),
                name="one_choice_per_thread_per_crossing",
            ),
        ),
    ]
