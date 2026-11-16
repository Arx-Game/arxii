"""Drop the per-level coefficient columns the pool and cap lanes replace (#5093).

Schema-only, the last of three (``0436_pools_and_caps_on_lanes_expand`` then
``0437_pools_and_caps_lane_rows``). Each column below was a coefficient multiplied by a level
in code; the lane's ``ModifierLevelBaseline`` rows now hold the same numbers, written by the
previous migration from each column's value before it goes.

Data disposition (ADR-0237): restructure. The four columns hold authored tuning that was
carried into lane rows (``anima_pool``, ``soul_tether_cap``, ``hollow_max``,
``techniques_per_gift``) by ``0437``, so no value is lost. Not reversible beyond re-adding the
columns at their defaults: the rows stay and the old values are not written back.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0437_pools_and_caps_lane_rows"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="animaconfig",
            name="maximum_per_level",
        ),
        migrations.RemoveField(
            model_name="giftacquisitionconfig",
            name="techniques_per_thread_level",
        ),
        migrations.RemoveField(
            model_name="soultetherconfig",
            name="hollow_max_level_mult",
        ),
        migrations.RemoveField(
            model_name="soultetherconfig",
            name="per_scene_cap_level_mult",
        ),
    ]
