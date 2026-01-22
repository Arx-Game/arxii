# Seed data moved to fixtures/initial_personality_distinctions.json
# Load with: python manage.py loaddata initial_personality_distinctions

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("distinctions", "0003_refactor_simplify_models"),
    ]

    operations = [
        # Data seeding moved to fixture: distinctions/fixtures/initial_personality_distinctions.json
        # Run: arx manage loaddata initial_personality_distinctions
    ]
