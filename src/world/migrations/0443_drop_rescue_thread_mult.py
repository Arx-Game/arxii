"""Drop the rescue budget's per-thread-level coefficient the rescue lane replaces (#5093).

Schema-only, the last of three (``0434_vow_and_facet_lanes_expand`` then
``0435_vow_and_facet_lane_rows``). ``SoulTetherConfig.rescue_budget_thread_mult_hundredths``
was a coefficient multiplied by a thread level in code; the ``rescue_budget_thread`` lane's
``ModifierLevelBaseline`` rows now hold the same number a rung, written by the previous
migration from the column's value before it goes.

Data disposition (ADR-0237): restructure. The column holds authored tuning that was carried
into lane rows by ``0435``, so no value is lost. Not reversible beyond re-adding the column at
its default: the rows stay and the old value is not written back.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0442_vow_and_facet_lane_rows"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="soultetherconfig",
            name="rescue_budget_thread_mult_hundredths",
        ),
    ]
