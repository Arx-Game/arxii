"""Delete the Ritual row of the removed Rite of Atonement (#4751).

Data only (the schema changes are in 0448).

The Rite of Atonement dispatched to ``world.magic.services.atonement.perform_atonement_rite``,
which this change removes. Ritual dispatch called it with arguments it did not accept, so no
player ever performed it, and a Ritual row still naming it would point at a function that no
longer exists. Disposition (ADR-0237): deliberate discard of authored content for a rite that
could not be performed.

For each Ritual row with that service path:

- Rows that are part of the ritual's own definition (component requirements, check config,
  liturgy, knowledge rows) go with it through their CASCADE foreign keys.
- Transient coordination rows (an in-progress session with its participants and references,
  a pending ceremony effect) are deleted first, because they PROTECT the ritual and exist
  only while a ritual is under way.
- Any other row that PROTECTs the ritual (an anima contribution, a class level advancement,
  a technique grant, a room feature install rite, a relationship capstone, a sustained
  action, or the drift correction config naming it as its rite) is history, play state or
  authored configuration. It is never deleted: the ritual is left in place and its id and
  the blocking tables are printed, so a person decides. A protecting relation this list
  does not know is caught the same way, so the migration never fails on a protected row.

Reversing does nothing: the row is not recreated.
"""

from django.db import migrations
from django.db.models import ProtectedError

SERVICE_PATH = "world.magic.services.atonement.perform_atonement_rite"

# Rows that exist only while a ritual is under way: deleted with the ritual.
TRANSIENT_MODELS = ("RitualSession", "PendingRitualEffect")

# History and authored configuration that PROTECT the ritual: never deleted.
PROTECTING_MODELS = (
    "ClassLevelAdvancement",
    "RitualAnimaContribution",
    "TechniqueGrant",
    "RoomFeatureKindInstallRitual",
    "RelationshipCapstone",
    "SustainedAction",
)


def delete_atonement_ritual(apps, schema_editor):
    Ritual = apps.get_model("arxii", "Ritual")
    for ritual in Ritual.objects.filter(service_function_path=SERVICE_PATH):
        blocking = [
            name
            for name in PROTECTING_MODELS
            if apps.get_model("arxii", name).objects.filter(ritual=ritual).exists()
        ]
        drift_config = apps.get_model("arxii", "DriftCorrectionConfig")
        if drift_config.objects.filter(rite=ritual).exists():
            blocking.append("DriftCorrectionConfig")
        if blocking:
            print(
                f"\n  Ritual {ritual.pk} ({ritual.name!r}) kept: still protected by "
                f"{', '.join(blocking)}."
            )
            continue
        for name in TRANSIENT_MODELS:
            apps.get_model("arxii", name).objects.filter(ritual=ritual).delete()
        try:
            ritual.delete()
        except ProtectedError as error:
            tables = sorted({type(row).__name__ for row in error.protected_objects})
            print(
                f"\n  Ritual {ritual.pk} ({ritual.name!r}) kept: protected by {', '.join(tables)}."
            )


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0448_remove_penance_and_atonement_rite"),
    ]

    operations = [
        migrations.RunPython(delete_atonement_ritual, migrations.RunPython.noop),
    ]
