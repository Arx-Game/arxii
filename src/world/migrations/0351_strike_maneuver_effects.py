"""The basic Strike's maneuver effect rows (#4858).

Data only (0350 adds the four keys to the choices). Get-or-create the four new
ManeuverEffect rows with today's numbers, so staff can see and change them before the
first Strike or miss reads them: the Strike's base damage, bare-hands damage, the
intensity a miss gains and the to-hit each point of intensity adds. These are prose-free
mechanical catalog rows the code reads by key (owner ruling 2026-10-22, the 0334
pattern). An existing row keeps its base value.

The values are copied here, never imported from app code. Reversing is a no-op: the rows
are harmless to keep, and reversing 0350 does not remove a key's row.
"""

from django.db import migrations

# world.mechanics.constants.MANEUVER_EFFECT_DEFAULTS for these keys as of #4858.
STRIKE_MANEUVER_EFFECT_DEFAULTS = {
    "strike_base_damage": 3,
    "strike_bare_hands_damage": 2,
    "miss_intensity": 1,
    "intensity_to_hit": 1,
}


def write_strike_catalog_rows(apps, schema_editor):
    ManeuverEffect = apps.get_model("arxii", "ManeuverEffect")
    for key, base_value in STRIKE_MANEUVER_EFFECT_DEFAULTS.items():
        ManeuverEffect.objects.get_or_create(key=key, defaults={"base_value": base_value})


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0350_strike_choices"),
    ]

    operations = [
        migrations.RunPython(write_strike_catalog_rows, migrations.RunPython.noop),
    ]
