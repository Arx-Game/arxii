"""Untyped damage is Physical (#4742): point the vitals config at the Physical row.

Data-only (the field is added in 0310). Production authors a DamageType named
"Physical"; an empty database has none, and the field stays null there until the
seeder or staff set it. Reversing is a no-op: reversing 0310 drops the field.
"""

from django.db import migrations

PHYSICAL_DAMAGE_TYPE_NAME = "Physical"


def set_physical_damage_type(apps, schema_editor):
    DamageType = apps.get_model("arxii", "DamageType")
    VitalsConsequenceConfig = apps.get_model("arxii", "VitalsConsequenceConfig")
    physical = DamageType.objects.filter(name=PHYSICAL_DAMAGE_TYPE_NAME).first()
    if physical is None:
        return
    # Production holds the singleton; a database without one gets the field from the
    # survivability seeder or staff instead (this migration never creates the row).
    VitalsConsequenceConfig.objects.filter(pk=1, physical_damage_type__isnull=True).update(
        physical_damage_type=physical
    )


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0310_physical_damage_type_and_damage_dealt_modifier"),
    ]

    operations = [
        migrations.RunPython(set_physical_damage_type, migrations.RunPython.noop),
    ]
