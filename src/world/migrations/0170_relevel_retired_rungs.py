# Data only (#4085): rows at the retired levels move to Barony (40). City (40) absorbed
# Barony (46), and Region (50) was never a size: the two production rows at it are
# title seats, and a seat is a barony (ADR-0310). An elevation requirement or build
# grant at a retired level takes the same rung; a requirement already at 40 wins over
# a retired duplicate (to_level is unique). Authored rows are updated, never dropped.

from django.db import migrations

RETIRED = (46, 50)
BARONY = 40


def relevel(apps, schema_editor):
    Area = apps.get_model("arxii", "Area")
    AreaBuildGrant = apps.get_model("arxii", "AreaBuildGrant")
    AreaElevationRequirement = apps.get_model("arxii", "AreaElevationRequirement")

    Area.objects.filter(level__in=RETIRED).update(level=BARONY)
    # A retired parent over a former City ends up level with its child, which Area.clean
    # refuses on the next save; better to stop the deploy here than to leave a row that
    # can never be saved again. Production has no such pair (checked 2026-09-30).
    from django.db.models import F  # noqa: PLC0415

    stuck = list(
        Area.objects.filter(parent__isnull=False, level__gte=F("parent__level")).values_list(
            "pk", "name", "level", "parent__name", "parent__level"
        )
    )
    if stuck:
        msg = f"re-level left a child at or above its parent's level: {stuck}"
        raise RuntimeError(msg)
    AreaBuildGrant.objects.filter(max_level__in=RETIRED).update(max_level=BARONY)
    retired = AreaElevationRequirement.objects.filter(to_level__in=RETIRED).order_by("to_level")
    if AreaElevationRequirement.objects.filter(to_level=BARONY).exists():
        retired.delete()
        return
    first = retired.first()
    if first is not None:
        AreaElevationRequirement.objects.filter(pk=first.pk).update(to_level=BARONY)
        retired.exclude(pk=first.pk).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0169_gossip_reach_and_barony"),
    ]

    operations = [
        migrations.RunPython(relevel, migrations.RunPython.noop),
    ]
