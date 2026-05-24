"""Seed the social_engagement KudosSourceCategory used by SceneActionRequest accepts.

Ported from main's original 0002 after the 2026-05-24 migration rebuild.
Reference-data seed — fresh deploys need this row to exist before any
scene-action-accept flow runs. Idempotent via update_or_create.
"""

from django.db import migrations


def create_social_engagement_category(apps, schema_editor):
    KudosSourceCategory = apps.get_model("progression", "KudosSourceCategory")
    KudosSourceCategory.objects.update_or_create(
        name="social_engagement",
        defaults={
            "display_name": "Social Engagement",
            "description": "Awarded for accepting another character's scene action request.",
            "default_amount": 1,
            "is_active": True,
            "staff_only": False,
        },
    )


def remove_social_engagement_category(apps, schema_editor):
    KudosSourceCategory = apps.get_model("progression", "KudosSourceCategory")
    KudosSourceCategory.objects.filter(name="social_engagement").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("progression", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(
            create_social_engagement_category,
            remove_social_engagement_category,
        ),
    ]
