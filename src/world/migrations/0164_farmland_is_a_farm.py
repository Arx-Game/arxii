# Data-only (#4060 slice 2): the seeded "Farmland PLACEHOLDER" holding kind was a coin
# stream named farm, while agriculture's FIELD feature was the farm that grew food. One
# farm, not two: the kind becomes a farm that sits on a field. Existing holdings of the
# kind keep their streams and stand nowhere yet (they yield nothing until a field is
# attached in play with ``site_holding``); no row is removed (ADR-0237: restructure).

from django.db import migrations


def farmland_is_a_farm(apps, schema_editor):
    HoldingKind = apps.get_model("arxii", "HoldingKind")
    HoldingKind.objects.filter(name="Farmland PLACEHOLDER").update(
        site_kind="land", requires_field=True, units_required=1
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0163_holding_sites"),
    ]

    operations = [
        migrations.RunPython(farmland_is_a_farm, noop),
    ]
