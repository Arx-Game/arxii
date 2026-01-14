"""
Data migration to populate Gender model with initial options.

Male, Female, and Non-binary/Other are the three gender options
available during character creation.
"""

from django.db import migrations


def populate_genders(apps, schema_editor):
    """Create initial gender options."""
    Gender = apps.get_model("character_sheets", "Gender")
    genders = [
        {"key": "male", "display_name": "Male", "is_default": False},
        {"key": "female", "display_name": "Female", "is_default": False},
        {"key": "nonbinary", "display_name": "Non-binary/Other", "is_default": True},
    ]
    for gender_data in genders:
        Gender.objects.get_or_create(key=gender_data["key"], defaults=gender_data)


def reverse_genders(apps, schema_editor):
    """Remove initial gender options (reversible migration)."""
    Gender = apps.get_model("character_sheets", "Gender")
    Gender.objects.filter(key__in=["male", "female", "nonbinary"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("character_sheets", "0002_charactersheet_pronouns"),
    ]

    operations = [
        migrations.RunPython(populate_genders, reverse_genders),
    ]
