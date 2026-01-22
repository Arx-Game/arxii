"""
Data migration to populate Gender model with initial options.
NOTE: Data now loaded via fixtures (initial_genders.json). Migration kept for history.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("character_sheets", "0002_charactersheet_pronouns"),
    ]

    operations = [
        # Data migration converted to no-op. Load data via:
        # arx manage loaddata initial_genders
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
    ]
