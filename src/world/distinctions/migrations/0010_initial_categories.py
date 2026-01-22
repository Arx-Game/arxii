# Generated manually for initial distinction categories

from django.db import migrations


def create_initial_categories(apps, schema_editor):
    """Create the 6 initial distinction categories."""
    DistinctionCategory = apps.get_model("distinctions", "DistinctionCategory")

    categories = [
        {
            "name": "Physical",
            "slug": "physical",
            "description": (
                "Distinctions related to physical attributes, health, and bodily "
                "characteristics. Includes advantages and disadvantages affecting "
                "strength, agility, endurance, appearance, and physical capabilities."
            ),
            "display_order": 1,
        },
        {
            "name": "Mental",
            "slug": "mental",
            "description": (
                "Distinctions related to mental faculties, intelligence, and cognitive "
                "abilities. Includes advantages and disadvantages affecting memory, "
                "reasoning, perception, and mental resilience."
            ),
            "display_order": 2,
        },
        {
            "name": "Personality",
            "slug": "personality",
            "description": (
                "Distinctions related to temperament, behavior patterns, and personal "
                "traits. Includes advantages and disadvantages affecting social "
                "interactions, emotional responses, and character tendencies."
            ),
            "display_order": 3,
        },
        {
            "name": "Social",
            "slug": "social",
            "description": (
                "Distinctions related to social standing, connections, and influence. "
                "Includes advantages and disadvantages affecting reputation, alliances, "
                "enemies, and position in society."
            ),
            "display_order": 4,
        },
        {
            "name": "Background",
            "slug": "background",
            "description": (
                "Distinctions related to a character's history, upbringing, and life "
                "experiences. Includes advantages and disadvantages from past events, "
                "training, education, and formative experiences."
            ),
            "display_order": 5,
        },
        {
            "name": "Arcane",
            "slug": "arcane",
            "description": (
                "Distinctions related to magical abilities, supernatural connections, "
                "and otherworldly influences. Includes advantages and disadvantages "
                "affecting magical aptitude, spiritual connections, and arcane phenomena."
            ),
            "display_order": 6,
        },
    ]

    for category_data in categories:
        DistinctionCategory.objects.get_or_create(
            slug=category_data["slug"],
            defaults=category_data,
        )


def reverse_initial_categories(apps, schema_editor):
    """Remove the 6 initial distinction categories."""
    DistinctionCategory = apps.get_model("distinctions", "DistinctionCategory")

    slugs = ["physical", "mental", "personality", "social", "background", "arcane"]
    DistinctionCategory.objects.filter(slug__in=slugs).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("distinctions", "0009_characterdistinctionother"),
    ]

    operations = [
        migrations.RunPython(create_initial_categories, reverse_initial_categories),
    ]
