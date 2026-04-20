# Generated for Resonance Pivot Spec A §2.2 — CharacterResonance merge.
#
# Reshapes CharacterResonance into a unified identity + currency row.
#   - Drops legacy fields: scope, strength, is_active, created_at.
#   - Drops the old FK to ObjectDB ("character") and replaces it with a FK to
#     CharacterSheet ("character_sheet") per the project rule "Avoid direct
#     FKs to ObjectDB".
#   - Adds the merged-in currency fields: balance, lifetime_earned,
#     claimed_at (replaces the old "created_at").
#   - Updates unique_together to (character_sheet, resonance).
#
# Per Spec A §7.1, no live data exists for this model, so this migration
# performs a structural drop/add rather than preserving rows.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("character_sheets", "0001_initial"),
        ("magic", "0017_threadweavingunlock_threadweaving_no_capstone"),
    ]

    operations = [
        # 1. Drop the unique_together that references the soon-to-be-removed
        #    "character" FK so we can remove that FK cleanly.
        migrations.AlterUniqueTogether(
            name="characterresonance",
            unique_together=set(),
        ),
        # 2. Drop legacy fields (no consumers post-merge).
        migrations.RemoveField(
            model_name="characterresonance",
            name="scope",
        ),
        migrations.RemoveField(
            model_name="characterresonance",
            name="strength",
        ),
        migrations.RemoveField(
            model_name="characterresonance",
            name="is_active",
        ),
        migrations.RemoveField(
            model_name="characterresonance",
            name="created_at",
        ),
        # 3. Re-FK character → character_sheet.
        migrations.RemoveField(
            model_name="characterresonance",
            name="character",
        ),
        migrations.AddField(
            model_name="characterresonance",
            name="character_sheet",
            field=models.ForeignKey(
                help_text="The character sheet this resonance is attached to.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="resonances",
                to="character_sheets.charactersheet",
            ),
            # Default not needed — table is empty per Spec A §7.1.
            preserve_default=False,
        ),
        # 4. Add the merged-in currency fields.
        migrations.AddField(
            model_name="characterresonance",
            name="balance",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Spendable resonance currency.",
            ),
        ),
        migrations.AddField(
            model_name="characterresonance",
            name="lifetime_earned",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Monotonic total of resonance earned (never decremented).",
            ),
        ),
        migrations.AddField(
            model_name="characterresonance",
            name="claimed_at",
            field=models.DateTimeField(
                auto_now_add=True,
                help_text=("When this resonance row was created (claimed by the character)."),
            ),
        ),
        # 5. Restore the unique constraint on the new FK pair.
        migrations.AlterUniqueTogether(
            name="characterresonance",
            unique_together={("character_sheet", "resonance")},
        ),
    ]
