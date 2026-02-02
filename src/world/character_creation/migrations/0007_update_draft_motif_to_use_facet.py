"""Update DraftMotifResonanceAssociation to use Facet instead of ResonanceAssociation.

No production data exists, so we truncate the table and recreate with new schema.
This migration MUST run before magic.0020 which deletes ResonanceAssociation.
"""

from django.db import migrations, models
import django.db.models.deletion


def clear_draft_motif_associations(apps, schema_editor):
    """Delete all draft motif associations before schema change."""
    DraftMotifResonanceAssociation = apps.get_model(
        "character_creation", "DraftMotifResonanceAssociation"
    )
    DraftMotifResonanceAssociation.objects.all().delete()


class Migration(migrations.Migration):
    """Update DraftMotifResonanceAssociation to use Facet."""

    dependencies = [
        ("character_creation", "0006_remove_characterdraft_draft_anima_ritual_and_more"),
        ("magic", "0018_add_character_facet"),  # Depend on Facet model existing
    ]

    operations = [
        # First, delete all existing records (no prod data)
        migrations.RunPython(clear_draft_motif_associations, migrations.RunPython.noop),
        # Remove old unique constraint
        migrations.AlterUniqueTogether(
            name="draftmotifresonanceassociation",
            unique_together=set(),
        ),
        # Remove old field (FK to ResonanceAssociation)
        migrations.RemoveField(
            model_name="draftmotifresonanceassociation",
            name="association",
        ),
        # Update related_name on motif_resonance field
        migrations.AlterField(
            model_name="draftmotifresonanceassociation",
            name="motif_resonance",
            field=models.ForeignKey(
                help_text="The draft motif resonance this facet belongs to.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="facet_assignments",
                to="character_creation.draftmotifresonance",
            ),
        ),
        # Add new field (FK to Facet)
        migrations.AddField(
            model_name="draftmotifresonanceassociation",
            name="facet",
            field=models.ForeignKey(
                default=1,  # Temporary default, will be removed
                help_text="The facet imagery.",
                on_delete=django.db.models.deletion.PROTECT,
                to="magic.facet",
            ),
            preserve_default=False,
        ),
        # Add new unique constraint
        migrations.AlterUniqueTogether(
            name="draftmotifresonanceassociation",
            unique_together={("motif_resonance", "facet")},
        ),
        # Update verbose names
        migrations.AlterModelOptions(
            name="draftmotifresonanceassociation",
            options={
                "verbose_name": "Draft Motif Resonance Facet",
                "verbose_name_plural": "Draft Motif Resonance Facets",
            },
        ),
    ]
