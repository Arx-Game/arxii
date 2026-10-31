"""The maneuver effect catalog's rows, and FleeConfig.cover_bonus carried into it (#4783).

Data only (the ManeuverEffect table and the ModifierTarget scope columns come from 0328 and
0329; 0331 drops FleeConfig.cover_bonus).

1. Get-or-create the "maneuver_effect" ModifierCategory and the eight ManeuverEffect rows
   with today's numbers. These are prose-free mechanical catalog rows the code reads by
   key (owner ruling 2026-10-22: such rows may ship by data migration), so production
   has them without a seeder run. An existing row keeps its base value.
2. ADR-0237 restructure: if a FleeConfig row exists, its cover_bonus becomes the base
   value of "Cover: escape bonus", so a staff-edited escape bonus survives the drop.

The values are copied here, never imported from app code. Reversing is a no-op: reversing
0328 drops the table, and 0331 reversed restores cover_bonus at its default.
"""

from django.db import migrations

MANEUVER_EFFECT_CATEGORY_NAME = "maneuver_effect"
CATEGORY_DESCRIPTION = (
    "Targets for the numbers a combat maneuver has (Charge damage, Cover escape bonus, "
    "partial protection and so on). Scope each target to one effect or one kind of effect."
)
COVER_ESCAPE_BONUS = "cover_escape_bonus"
# world.mechanics.constants.MANEUVER_EFFECT_DEFAULTS as of #4783.
MANEUVER_EFFECT_DEFAULTS = {
    "charge_to_hit": 10,
    "charge_damage": 5,
    "charge_reach": 5,
    COVER_ESCAPE_BONUS: 10,
    "succor_partial_protection": 50,
    "interpose_partial_protection": 50,
    "rally_morale": 15,
    "rally_surge_intensity": 100,
}


def write_catalog_and_carry_cover_bonus(apps, schema_editor):
    ModifierCategory = apps.get_model("arxii", "ModifierCategory")
    ManeuverEffect = apps.get_model("arxii", "ManeuverEffect")
    FleeConfig = apps.get_model("arxii", "FleeConfig")

    ModifierCategory.objects.get_or_create(
        name=MANEUVER_EFFECT_CATEGORY_NAME,
        defaults={"description": CATEGORY_DESCRIPTION},
    )
    for key, base_value in MANEUVER_EFFECT_DEFAULTS.items():
        ManeuverEffect.objects.get_or_create(key=key, defaults={"base_value": base_value})

    flee_config = FleeConfig.objects.order_by("pk").first()
    if flee_config is None:
        return
    ManeuverEffect.objects.filter(key=COVER_ESCAPE_BONUS).update(base_value=flee_config.cover_bonus)


class Migration(migrations.Migration):
    dependencies = [("arxii", "0329_modifier_target_one_scope")]

    operations = [
        migrations.RunPython(write_catalog_and_carry_cover_bonus, migrations.RunPython.noop),
    ]
