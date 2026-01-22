# Seed data moved to fixtures/initial_goal_domains.json
# Load with: python manage.py loaddata initial_goal_domains

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("goals", "0001_initial"),
    ]

    operations = [
        # Data seeding moved to fixture: goals/fixtures/initial_goal_domains.json
        # Run: arx manage loaddata initial_goal_domains
    ]
