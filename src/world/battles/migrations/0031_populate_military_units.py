"""Data migration: populate MilitaryUnit from existing BattleUnit rows.

For each BattleUnit, creates a corresponding MilitaryUnit copying all identity
and stat fields, then sets BattleUnit.military_unit FK. Also copies
BattleUnitCapability rows to MilitaryUnitCapability and re-points the
properties M2M.

This is the bridge migration — after it runs, the schema migration that
removes the old BattleUnit fields can safely execute.
"""

from django.db import migrations


def transfer_battleunit_data_to_militaryunit(apps, schema_editor):
    """Create MilitaryUnit from each BattleUnit, copy capabilities + properties."""
    BattleUnit = apps.get_model("battles", "BattleUnit")
    MilitaryUnit = apps.get_model("military", "MilitaryUnit")
    MilitaryUnitCapability = apps.get_model("military", "MilitaryUnitCapability")
    BattleUnitCapability = apps.get_model("battles", "BattleUnitCapability")

    for bu in BattleUnit.objects.all():
        mu = MilitaryUnit.objects.create(
            name=bu.name,
            descriptor=bu.descriptor,
            commander_id=bu.commander_id,
            summoned_by_id=bu.summoned_by_id,
            quality=bu.quality,
            strength=bu.strength,
            morale=bu.morale,
            individual_count=bu.individual_count,
        )
        bu.military_unit = mu
        bu.save(update_fields=["military_unit"])

        # Copy capabilities
        for buc in BattleUnitCapability.objects.filter(unit=bu):
            MilitaryUnitCapability.objects.create(
                unit=mu,
                capability_id=buc.capability_id,
                value=buc.value,
            )

        # Copy properties M2M
        for prop in bu.properties.all():
            mu.properties.add(prop)


def reverse_military_units(apps, schema_editor):
    """Reverse: delete MilitaryUnit rows created by this migration."""
    MilitaryUnit = apps.get_model("military", "MilitaryUnit")
    MilitaryUnit.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("battles", "0030_battleunit_military_unit"),
        ("military", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(transfer_battleunit_data_to_militaryunit, reverse_military_units),
    ]
