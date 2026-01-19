"""
Add Perception stat to primary statistics.

Adds the 9th primary stat: Perception (social category).
"""

from django.db import migrations


def create_perception_stat(apps, schema_editor):
    """Create the Perception stat Trait record."""
    Trait = apps.get_model("traits", "Trait")

    Trait.objects.get_or_create(
        name="perception",
        defaults={
            "trait_type": "stat",
            "category": "social",
            "description": "Awareness and reading of people and situations.",
            "is_public": True,
        },
    )


def reverse_perception_stat(apps, schema_editor):
    """Remove Perception stat."""
    Trait = apps.get_model("traits", "Trait")
    Trait.objects.filter(name="perception").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("traits", "0003_alter_pointconversionrange_trait_type_and_more"),
    ]

    operations = [
        migrations.RunPython(create_perception_stat, reverse_perception_stat),
    ]
