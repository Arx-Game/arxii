# Data only (#4085): rows at the retired levels move to Barony (40). City (40) absorbed
# Barony (46), and Region (50) was never a size: the two production rows at it are
# title seats, and a seat is a barony (ADR-0310). An elevation requirement or build
# grant at a retired level takes the same rung; a requirement already at 40 wins over
# a retired duplicate (to_level is unique). Authored rows are updated, never dropped.
#
# A retired row that holds a Barony or larger cannot drop to 40 without sitting level
# with its own child, which Area.clean refuses. Production had one: Arvum (Region) over
# Arx (City), authored after the 2026-09-30 check, and it failed the 2026-10-03 deploy.
# Such a row takes the lowest live rung above its tallest child instead (Arvum ->
# County); staff re-level it from the admin if that rung is wrong. Rows are re-levelled
# deepest first, so a retired row over another retired row sees its child's new level.

from collections import defaultdict

from django.db import migrations
from django.db.models import F

RETIRED = (46, 50)
BARONY = 40
# AreaLevel's live rungs from Barony up, frozen here as the migration saw them.
RUNGS_FROM_BARONY = (40, 53, 56, 60, 65, 70, 80, 90)


def relevel(apps, schema_editor):
    Area = apps.get_model("arxii", "Area")
    AreaBuildGrant = apps.get_model("arxii", "AreaBuildGrant")
    AreaElevationRequirement = apps.get_model("arxii", "AreaElevationRequirement")

    levels = {}
    parents = {}
    children = defaultdict(list)
    for pk, level, parent_id in Area.objects.values_list("pk", "level", "parent_id"):
        levels[pk] = level
        parents[pk] = parent_id
        if parent_id is not None:
            children[parent_id].append(pk)

    def depth(pk):
        steps = 0
        while parents[pk] is not None:
            pk = parents[pk]
            steps += 1
        return steps

    moves = defaultdict(list)
    for pk in sorted(
        (pk for pk, level in levels.items() if level in RETIRED), key=depth, reverse=True
    ):
        tallest = max((levels[child] for child in children[pk]), default=0)
        levels[pk] = next(rung for rung in RUNGS_FROM_BARONY if rung > tallest)
        moves[levels[pk]].append(pk)
    for level, pks in moves.items():
        Area.objects.filter(pk__in=pks).update(level=level)

    # A retired row whose own parent sits at or below its new rung still breaks
    # Area.clean; better to stop the deploy here than to leave a row that can never be
    # saved again.
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
