# Add ModifierSource model and update CharacterModifier schema

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Add ModifierSource model and update CharacterModifier to use it.

    Also updates CharacterModifier.character FK from ObjectDB to CharacterSheet.
    Data was cleared in the previous migration.
    """

    dependencies = [
        ("character_sheets", "0001_initial"),
        ("conditions", "0001_initial"),
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
                        help_text="The effect template from a distinction",
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
                        help_text="The character's distinction that grants this source",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="modifier_sources",
                        to="distinctions.characterdistinction",
                    ),
                ),
                (
                    "condition_instance",
                    models.ForeignKey(
                        blank=True,
                        help_text="The condition instance that grants this source",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="modifier_sources",
                        to="conditions.conditioninstance",
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
                help_text="Source that grants this modifier",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="modifiers",
                to="mechanics.modifiersource",
            ),
            # Data was cleared, so this should work without default
            preserve_default=False,
        ),
        # Add related_name to modifier_type FK
        migrations.AlterField(
            model_name="charactermodifier",
            name="modifier_type",
            field=models.ForeignKey(
                help_text="What type of modifier this is",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="character_modifiers",
                to="mechanics.modifiertype",
            ),
        ),
    ]
