"""
Add primary statistics Trait records for character stats.

Creates 8 Trait records representing the primary stats:
- Physical: Strength, Agility, Stamina
- Social: Charm, Presence
- Mental: Intellect, Wits, Willpower
"""

from django.db import migrations


def create_primary_stats(apps, schema_editor):
    """Create the 8 primary stat Trait records."""
    Trait = apps.get_model("traits", "Trait")

    stats = [
        ("strength", "physical", "Raw physical power and muscle."),
        ("agility", "physical", "Speed, reflexes, and coordination."),
        ("stamina", "physical", "Endurance and resistance to harm."),
        ("charm", "social", "Likability and social magnetism."),
        ("presence", "social", "Force of personality and leadership."),
        ("intellect", "mental", "Reasoning and learned knowledge."),
        ("wits", "mental", "Quick thinking and situational awareness."),
        ("willpower", "mental", "Mental fortitude and determination."),
    ]

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
    stat_names = [
        "strength",
        "agility",
        "stamina",
        "charm",
        "presence",
        "intellect",
        "wits",
        "willpower",
    ]
    Trait.objects.filter(name__in=stat_names).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("traits", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_primary_stats, reverse_primary_stats),
    ]
