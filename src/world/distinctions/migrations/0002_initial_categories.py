# Generated manually for initial distinction categories
# NOTE: Data now loaded via fixtures (initial_categories.json). Migration kept for history.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("distinctions", "0001_initial"),
    ]

    operations = [
        # Data migration converted to no-op. Load data via:
        # arx manage loaddata initial_categories
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
    ]
