"""
Data migration to remove duplicate DistinctionEffect records.

A fixture was accidentally loaded twice, creating duplicate effects for several
distinctions (Indolent, Tireless, Efficient, Giant's Blood, Spoiled).

This migration identifies and removes duplicate effects by:
1. Grouping effects by (distinction_id, description)
2. Keeping the effect with the lowest ID (the original)
3. Deleting any duplicates with higher IDs
"""

from django.db import migrations


def remove_duplicate_effects(apps, schema_editor):
    """Remove duplicate DistinctionEffect records, keeping the one with lowest ID."""
    DistinctionEffect = apps.get_model("distinctions", "DistinctionEffect")

    # Find all effects grouped by distinction and description
    seen = {}  # (distinction_id, description) -> lowest effect ID
    duplicates_to_delete = []

    for effect in DistinctionEffect.objects.order_by("id"):
        key = (effect.distinction_id, effect.description)
        if key in seen:
            # This is a duplicate - mark for deletion
            duplicates_to_delete.append(effect.id)
        else:
            # First occurrence - keep this one
            seen[key] = effect.id

    # Delete duplicates
    if duplicates_to_delete:
        DistinctionEffect.objects.filter(id__in=duplicates_to_delete).delete()


def reverse_migration(apps, schema_editor):
    """
    Reverse migration is a no-op.

    We cannot restore deleted data, but since the duplicates were exact copies,
    no unique data was lost. The remaining effects contain all the information.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("distinctions", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(remove_duplicate_effects, reverse_migration),
    ]
