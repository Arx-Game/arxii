"""Write each moved pool and cap rule's lane rows from the coefficient it replaces (#5093).

Data-only, between ``0429_pools_and_caps_on_lanes_expand`` (the lanes and ``FatigueConfig``)
and ``0431_pools_and_caps_drop_coefficients`` (the columns go). Five rules were a coefficient
times a level in code; each is now one ``ModifierLevelBaseline`` row per level 1-30 on its own
lane, and this writes them, if missing, before the columns are dropped:

* ``anima_pool``: ``AnimaConfig.maximum_per_level`` x level (100 when the row is absent).
* ``soul_tether_cap``: ``SoulTetherConfig.per_scene_cap_level_mult`` x rung (2).
* ``hollow_max``: ``SoulTetherConfig.hollow_max_level_mult`` x rung (10).
* ``techniques_per_gift``: ``GiftAcquisitionConfig.techniques_per_thread_level`` x depth (3).
* ``outfit_trickle``: the rung itself, the factor ``max(1, rung)`` the trickle used (the level 1
  row covers rungs 0 and 1).

The ``fatigue_level_bonus`` lane gets no rows: fatigue capacity had no level term before, and a
lane with no rows adds nothing, so staff author its rows when they want a level bonus.

Every database is written to, not only one that holds a config row: a config row is created
the first time anything reads it, so a database can hold none yet still run the rules, and the
new code raises when a lane has no rows. A value staff edited on a config row is carried; a
lane row staff already wrote is kept as it is.

Data disposition (ADR-0237): restructure. The coefficients are authored tuning, and each is
carried into its lane's rows before ``0431`` drops the column. Not reversible beyond leaving
the rows: they are additive and harmless to the old schema.
"""

from django.db import migrations

# seed-data-ok: ADR-0237 restructure backfill. The numbers are each config column's current
# value (its default when the row is absent), written so the new lane reads reproduce today's
# behaviour; staff tune them in the rows afterwards.

_LEVELS = range(1, 31)

# lane, app model, config column and its default when the model has no row
_COEFFICIENT_LANES = (
    ("anima_pool", "AnimaConfig", "maximum_per_level", 100),
    ("soul_tether_cap", "SoulTetherConfig", "per_scene_cap_level_mult", 2),
    ("hollow_max", "SoulTetherConfig", "hollow_max_level_mult", 10),
    ("techniques_per_gift", "GiftAcquisitionConfig", "techniques_per_thread_level", 3),
)


def write_lane_rows(apps, schema_editor):
    ModifierLevelBaseline = apps.get_model("arxii", "ModifierLevelBaseline")

    def write(lane, per_level):
        for level in _LEVELS:
            ModifierLevelBaseline.objects.get_or_create(
                lane=lane, level=level, defaults={"baseline": per_level(level)}
            )

    for lane, model_name, column, default in _COEFFICIENT_LANES:
        row = apps.get_model("arxii", model_name).objects.order_by("pk").first()
        coefficient = getattr(row, column) if row is not None else default
        write(lane, lambda level, coefficient=coefficient: coefficient * level)
    write("outfit_trickle", lambda level: level)


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0429_pools_and_caps_on_lanes_expand"),
    ]

    operations = [
        migrations.RunPython(write_lane_rows, migrations.RunPython.noop),
    ]
