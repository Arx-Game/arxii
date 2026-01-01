# Generated manually

from django.db import migrations


def create_test_family(apps, schema_editor):
    """Create a test family for development purposes."""
    Family = apps.get_model("roster", "Family")
    Family.objects.get_or_create(
        name="TestFamily",
        defaults={
            "family_type": "commoner",
            "description": "A test family for development and testing purposes.",
            "is_playable": True,
            "created_by_cg": False,
        },
    )


def remove_test_family(apps, schema_editor):
    """Remove the test family."""
    Family = apps.get_model("roster", "Family")
    Family.objects.filter(name="TestFamily").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("roster", "0002_add_family_model"),
    ]

    operations = [
        migrations.RunPython(create_test_family, remove_test_family),
    ]
