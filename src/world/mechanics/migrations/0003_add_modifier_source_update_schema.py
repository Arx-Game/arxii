# Add ModifierSource model and update CharacterModifier schema

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Add ModifierSource model and update CharacterModifier to use it.

    ModifierSource tracks where a modifier came from (distinction effects, etc.).
    CharacterModifier.modifier_type is removed - it's now derived from
    source.distinction_effect.target.

    Also updates CharacterModifier.character FK from ObjectDB to CharacterSheet.
    Data was cleared in the previous migration.
    """

    dependencies = [
        ("character_sheets", "0001_initial"),
        ("distinctions", "0001_initial"),
        ("mechanics", "0002_clear_modifier_data"),
    ]

    operations = [
        # Create ModifierSource model
        migrations.CreateModel(
            name="ModifierSource",
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
                    "distinction_effect",
                    models.ForeignKey(
                        blank=True,
                        help_text="The effect template (defines modifier_type via effect.target)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="modifier_sources",
                        to="distinctions.distinctioneffect",
                    ),
                ),
                (
                    "character_distinction",
                    models.ForeignKey(
                        blank=True,
                        help_text="The character's distinction instance (for cascade deletion)",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="modifier_sources",
                        to="distinctions.characterdistinction",
                    ),
                ),
            ],
            options={
                "verbose_name": "Modifier source",
                "verbose_name_plural": "Modifier sources",
            },
        ),
        # Remove old source fields from CharacterModifier
        migrations.RemoveField(
            model_name="charactermodifier",
            name="source_distinction",
        ),
        migrations.RemoveField(
            model_name="charactermodifier",
            name="source_condition",
        ),
        # Remove modifier_type - now derived from source.distinction_effect.target
        migrations.RemoveField(
            model_name="charactermodifier",
            name="modifier_type",
        ),
        # Change character FK from ObjectDB to CharacterSheet
        migrations.AlterField(
            model_name="charactermodifier",
            name="character",
            field=models.ForeignKey(
                help_text="Character who has this modifier",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="modifiers",
                to="character_sheets.charactersheet",
            ),
        ),
        # Add source FK to CharacterModifier
        migrations.AddField(
            model_name="charactermodifier",
            name="source",
            field=models.ForeignKey(
                help_text="Source that grants this modifier (also defines modifier_type)",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="modifiers",
                to="mechanics.modifiersource",
            ),
            # Data was cleared, so this should work without default
            preserve_default=False,
        ),
    ]
