"""
Add Perception stat to primary statistics.
NOTE: Data now loaded via fixtures (initial_primary_stats.json). Migration kept for history.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("traits", "0003_alter_pointconversionrange_trait_type_and_more"),
    ]

    operations = [
        # Data migration converted to no-op. Load data via:
        # arx manage loaddata initial_primary_stats
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
    ]
