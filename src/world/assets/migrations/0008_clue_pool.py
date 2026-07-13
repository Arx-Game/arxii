"""Add CluePool + CluePoolEntry; swap AssetTaskIntelDetails.clue → clue_pool (#2293)."""

from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("assets", "0007_asset_task_intel_details"),
        ("clues", "0009_clue_target_persona_clue_target_persona_linked_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CluePool",
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
                    "name",
                    models.CharField(
                        help_text="Human-readable pool name (e.g., 'Rumors of Arx').",
                        max_length=100,
                        unique=True,
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="GM authoring context for this pool.",
                    ),
                ),
            ],
            options={
                "verbose_name": "Clue Pool",
                "verbose_name_plural": "Clue Pools",
            },
        ),
        migrations.CreateModel(
            name="CluePoolEntry",
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
                    "weight",
                    models.PositiveIntegerField(
                        default=1,
                        help_text=(
                            "Draw weight. Higher = more likely to be drawn. "
                            "Default 1 = uniform. Minimum 1."
                        ),
                        validators=[MinValueValidator(1)],
                    ),
                ),
                (
                    "pool",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entries",
                        to="assets.cluepool",
                    ),
                ),
                (
                    "clue",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="pool_entries",
                        to="clues.clue",
                    ),
                ),
            ],
            options={
                "verbose_name": "Clue Pool Entry",
                "verbose_name_plural": "Clue Pool Entries",
            },
        ),
        migrations.AddConstraint(
            model_name="cluepoolentry",
            constraint=models.UniqueConstraint(
                fields=["pool", "clue"],
                name="unique_clue_pool_entry",
            ),
        ),
        # Remove the old single-clue FK and add the new clue_pool FK.
        # No data migration — there is no existing production data.
        migrations.RemoveField(
            model_name="assettaskinteldetails",
            name="clue",
        ),
        migrations.AddField(
            model_name="assettaskinteldetails",
            name="clue_pool",
            field=models.ForeignKey(
                help_text="The pool of clues this intel task draws from.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="intel_task_offers",
                to="assets.cluepool",
            ),
        ),
    ]
