"""Write the rung lanes' rows (#5093).

Data-only, between ``0441_vow_and_facet_lanes_expand`` (the lanes and the renamed per-rung
columns) and ``0443_drop_rescue_thread_mult`` (the one coefficient column goes). Six rules read
a thread's rung through a ``ModifierLevelBaseline`` row per level 1-30 on their own lane, and
this writes the rows, if missing, before the column is dropped:

* ``rescue_budget_thread``: ``SoulTetherConfig.rescue_budget_thread_mult_hundredths`` x 10 x
  rung (5 when the row is absent, so 50 a rung): hundredths of the rescue budget's multiplier,
  what the 0.05 a thread level gave at each whole rung.
* ``moon_tuning``: 10 a rung, the 1 tuning a thread level ``TUNING_PER_THREAD_LEVEL`` gave
  (a code constant, so there is no column to carry).
* ``facet_effect_bonus``, ``vow_effect_severity``, ``vow_effect_duration`` and
  ``vow_effect_damage``: 10 a rung. The authored per-rung columns were renamed to tenths by
  ``0441`` with their numbers kept, so a lane that gains 10 a rung reads each as it did.

Every database is written to, not only one with a config row: the new code raises when a lane
has no rows. A value staff edited on the config row is carried; a lane row staff already
wrote is kept as it is.

Data disposition (ADR-0237): restructure. The one coefficient is authored tuning, carried into
its lane's rows before ``0443`` drops the column. Not reversible beyond leaving the rows: they
are additive and harmless to the old schema.
"""

from django.db import migrations

# seed-data-ok: ADR-0237 restructure backfill. The numbers are each coefficient's current value
# (its default when the row is absent), written so the new lane reads reproduce today's
# behaviour at each whole rung; staff tune them in the rows afterwards.

_LEVELS = range(1, 31)

# lane -> baseline per rung (the rescue lane's is carried from the config row below)
_FLAT_RUNG_LANES = (
    ("moon_tuning", 10),
    ("facet_effect_bonus", 10),
    ("vow_effect_severity", 10),
    ("vow_effect_duration", 10),
    ("vow_effect_damage", 10),
)
_RESCUE_DEFAULT_HUNDREDTHS = 5
_THREAD_LEVELS_PER_RUNG = 10


def write_lane_rows(apps, schema_editor):
    ModifierLevelBaseline = apps.get_model("arxii", "ModifierLevelBaseline")

    def write(lane, per_rung):
        for level in _LEVELS:
            ModifierLevelBaseline.objects.get_or_create(
                lane=lane, level=level, defaults={"baseline": per_rung * level}
            )

    config = apps.get_model("arxii", "SoulTetherConfig").objects.order_by("pk").first()
    hundredths = (
        config.rescue_budget_thread_mult_hundredths
        if config is not None
        else _RESCUE_DEFAULT_HUNDREDTHS
    )
    write("rescue_budget_thread", hundredths * _THREAD_LEVELS_PER_RUNG)
    for lane, per_rung in _FLAT_RUNG_LANES:
        write(lane, per_rung)


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0441_vow_and_facet_lanes_expand"),
    ]

    operations = [
        migrations.RunPython(write_lane_rows, migrations.RunPython.noop),
    ]
