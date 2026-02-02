# Generated manually for CharacterAnimaRitual redesign

from django.db import migrations, models
import django.db.models.deletion


def clear_existing_rituals(apps, schema_editor):
    """Remove existing CharacterAnimaRitual records before schema change."""
    CharacterAnimaRitual = apps.get_model("magic", "CharacterAnimaRitual")
    CharacterAnimaRitual.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("character_sheets", "0002_initial"),
        ("magic", "0010_add_motif_models"),
        ("mechanics", "0002_modifiertype_affiliated_affinity"),
        ("scenes", "0001_initial"),
        ("skills", "0001_initial"),
        ("traits", "0001_initial"),
    ]

    operations = [
        # Clear existing data before schema changes
        migrations.RunPython(clear_existing_rituals, migrations.RunPython.noop),
        # Remove unique_together constraint FIRST (before removing fields)
        migrations.AlterUniqueTogether(
            name="characteranimaritual",
            unique_together=set(),
        ),
        # Remove old fields from CharacterAnimaRitual
        migrations.RemoveField(
            model_name="characteranimaritual",
            name="ritual_type",
        ),
        migrations.RemoveField(
            model_name="characteranimaritual",
            name="personal_description",
        ),
        migrations.RemoveField(
            model_name="characteranimaritual",
            name="is_primary",
        ),
        migrations.RemoveField(
            model_name="characteranimaritual",
            name="times_performed",
        ),
        migrations.RemoveField(
            model_name="characteranimaritual",
            name="created_at",
        ),
        # Change character field from ForeignKey(ObjectDB) to OneToOneField(CharacterSheet)
        migrations.RemoveField(
            model_name="characteranimaritual",
            name="character",
        ),
        migrations.AddField(
            model_name="characteranimaritual",
            name="character",
            field=models.OneToOneField(
                help_text="The character this ritual belongs to.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="anima_ritual",
                to="character_sheets.charactersheet",
            ),
            preserve_default=False,
        ),
        # Add new fields
        migrations.AddField(
            model_name="characteranimaritual",
            name="stat",
            field=models.ForeignKey(
                help_text="The primary stat used in this ritual.",
                limit_choices_to={"trait_type": "stat"},
                on_delete=django.db.models.deletion.PROTECT,
                related_name="anima_rituals",
                to="traits.trait",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="characteranimaritual",
            name="skill",
            field=models.ForeignKey(
                help_text="The skill used in this ritual.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="anima_rituals",
                to="skills.skill",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="characteranimaritual",
            name="specialization",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional specialization for this ritual.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="anima_rituals",
                to="skills.specialization",
            ),
        ),
        migrations.AddField(
            model_name="characteranimaritual",
            name="resonance",
            field=models.ForeignKey(
                help_text="The resonance that powers this ritual.",
                limit_choices_to={"category__name": "resonance"},
                on_delete=django.db.models.deletion.PROTECT,
                related_name="anima_rituals",
                to="mechanics.modifiertype",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="characteranimaritual",
            name="description",
            field=models.TextField(
                default="",
                help_text="Social activity that restores anima.",
            ),
            preserve_default=False,
        ),
        # Create AnimaRitualPerformance model
        migrations.CreateModel(
            name="AnimaRitualPerformance",
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
                    "performed_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="When the ritual was performed.",
                    ),
                ),
                (
                    "was_successful",
                    models.BooleanField(
                        help_text="Whether the ritual succeeded.",
                    ),
                ),
                (
                    "anima_recovered",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Amount of anima recovered (if successful).",
                        null=True,
                    ),
                ),
                (
                    "notes",
                    models.TextField(
                        blank=True,
                        help_text="Optional notes about this performance.",
                    ),
                ),
                (
                    "ritual",
                    models.ForeignKey(
                        help_text="The ritual that was performed.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="performances",
                        to="magic.characteranimaritual",
                    ),
                ),
                (
                    "target_character",
                    models.ForeignKey(
                        help_text="The character the ritual was performed with.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="anima_ritual_participations",
                        to="character_sheets.charactersheet",
                    ),
                ),
                (
                    "scene",
                    models.ForeignKey(
                        blank=True,
                        help_text="The scene where this ritual was performed.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="anima_ritual_performances",
                        to="scenes.scene",
                    ),
                ),
            ],
            options={
                "verbose_name": "Anima Ritual Performance",
                "verbose_name_plural": "Anima Ritual Performances",
                "ordering": ["-performed_at"],
            },
        ),
    ]
