"""Add social_engagement KudosSourceCategory used by SceneActionRequest accepts."""

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
        ("progression", "0001_initial"),
    ]
    operations = [
        migrations.RunPython(
            create_social_engagement_category,
            remove_social_engagement_category,
        ),
    ]
