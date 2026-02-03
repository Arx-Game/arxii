"""Remove ResonanceAssociation model.

This model has been replaced by the hierarchical Facet model.
No production data exists, so we can safely delete the table.

IMPORTANT: This migration depends on character_creation.0007 which removes
the FK reference to ResonanceAssociation first.
"""

from django.db import migrations


class Migration(migrations.Migration):
    """Remove the deprecated ResonanceAssociation model."""

    dependencies = [
        ("magic", "0019_update_motif_resonance_association_to_facet"),
        # Must run AFTER character_creation removes its FK to ResonanceAssociation
        ("character_creation", "0007_update_draft_motif_to_use_facet"),
    ]

    operations = [
        migrations.DeleteModel(
            name="ResonanceAssociation",
        ),
    ]
