"""Release the old-column unique keys before the contract (#4681; schema only).

``ResonanceConversion`` and ``AuraAffinityThreshold`` are unique on a column the contract
step removes. Dropping the keys here, one migration ahead, lets the contract migration
reverse cleanly: rolling back re-adds the columns, 0305 refills them from the row-keyed
FKs, and only then does this migration put the keys back.

ADR-0237: no data is dropped; an index is released.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0303_affinity_rows_backfill"),
    ]

    operations = [
        migrations.AlterUniqueTogether(name="resonanceconversion", unique_together=set()),
        migrations.AlterUniqueTogether(name="auraaffinitythreshold", unique_together=set()),
    ]
