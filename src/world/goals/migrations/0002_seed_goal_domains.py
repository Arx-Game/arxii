# Generated manually for initial goal domains

from django.db import migrations


def create_goal_domains(apps, schema_editor):
    """Create the 6 goal domains."""
    GoalDomain = apps.get_model("goals", "GoalDomain")

    domains = [
        {
            "name": "Standing",
            "slug": "standing",
            "description": (
                "Political power, fame, legend, glory, and social position. "
                "Goals related to becoming recognized, gaining titles, winning "
                "tournaments, or being remembered."
            ),
            "display_order": 1,
            "is_optional": False,
        },
        {
            "name": "Wealth",
            "slug": "wealth",
            "description": (
                "Resources, property, luxury, and territory. Goals related to "
                "acquiring estates, cornering markets, treasure hunting, or "
                "accumulating material riches."
            ),
            "display_order": 2,
            "is_optional": False,
        },
        {
            "name": "Knowledge",
            "slug": "knowledge",
            "description": (
                "Secrets, lore, magical understanding, and information advantage. "
                "Goals related to learning forbidden magic, uncovering conspiracies, "
                "finding lost texts, or gaining insight others lack."
            ),
            "display_order": 3,
            "is_optional": False,
        },
        {
            "name": "Mastery",
            "slug": "mastery",
            "description": (
                "Skills, abilities, magical power, and being the best. Goals "
                "related to becoming the greatest swordsman, mastering a spell "
                "school, or achieving peak performance in any discipline."
            ),
            "display_order": 4,
            "is_optional": False,
        },
        {
            "name": "Bonds",
            "slug": "bonds",
            "description": (
                "Relationships, loyalty, and people bound to them. Goals related "
                "to protecting family, building a loyal retinue, finding love, "
                "or cultivating meaningful connections."
            ),
            "display_order": 5,
            "is_optional": False,
        },
        {
            "name": "Needs",
            "slug": "needs",
            "description": (
                "Things you can't live without. An optional domain for characters "
                "with compulsions, addictions, or requirements like blood for "
                "vampires, drugs, thrills, or gambling."
            ),
            "display_order": 6,
            "is_optional": True,
        },
    ]

    for domain_data in domains:
        GoalDomain.objects.get_or_create(
            slug=domain_data["slug"],
            defaults=domain_data,
        )


def reverse_goal_domains(apps, schema_editor):
    """Remove the 6 goal domains."""
    GoalDomain = apps.get_model("goals", "GoalDomain")

    slugs = ["standing", "wealth", "knowledge", "mastery", "bonds", "needs"]
    GoalDomain.objects.filter(slug__in=slugs).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("goals", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_goal_domains, reverse_goal_domains),
    ]
