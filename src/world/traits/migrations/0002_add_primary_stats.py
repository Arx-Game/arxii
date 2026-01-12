"""
Add primary statistics Trait records for character stats.

Creates 8 Trait records representing the primary stats:
- Physical: Strength, Agility, Stamina
- Social: Charm, Presence
- Mental: Intellect, Wits, Willpower
"""

from django.db import migrations

# Import stat metadata at module level to avoid import during migration
from world.traits.constants import PrimaryStat


def create_primary_stats(apps, schema_editor):
    """Create the 8 primary stat Trait records."""
    Trait = apps.get_model("traits", "Trait")

    stats = PrimaryStat.get_stat_metadata()

    for name, category, description in stats:
        Trait.objects.get_or_create(
            name=name,
            defaults={
                "trait_type": "stat",
                "category": category,
                "description": description,
                "is_public": True,
            },
        )


def reverse_primary_stats(apps, schema_editor):
    """Remove primary stats."""
    Trait = apps.get_model("traits", "Trait")
    stat_names = PrimaryStat.get_all_stat_names()
    Trait.objects.filter(name__in=stat_names).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("traits", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_primary_stats, reverse_primary_stats),
    ]
