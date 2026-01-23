"""
Add primary statistics Trait records for character stats.
NOTE: Data now loaded via fixtures (initial_primary_stats.json). Migration kept for history.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("traits", "0001_initial"),
    ]

    operations = [
        # Data migration converted to no-op. Load data via:
        # arx manage loaddata initial_primary_stats
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
    ]
