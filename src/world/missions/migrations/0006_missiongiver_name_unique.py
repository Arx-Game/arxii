# Hand-written migration — add unique constraint to MissionGiver.name.
# Dropped slug in 0005; name takes over as canonical human identifier.
# Hand-written because `arx manage migrate` hangs on the Evennia
# superuser-creation wizard in this devcontainer.
#
# Includes a defensive RunPython step that auto-suffixes any
# duplicate names before applying the constraint. On fresh DBs (CI,
# new environments) this is a no-op; on any environment that
# somehow accumulated duplicates, it makes the migration apply
# cleanly instead of failing at the constraint step.

from collections import defaultdict

from django.db import migrations, models


def dedupe_giver_names(apps, schema_editor):
    """Suffix any duplicate MissionGiver.name values before unique=True applies."""
    MissionGiver = apps.get_model("missions", "MissionGiver")
    seen_names: dict[str, int] = defaultdict(int)
    for giver in MissionGiver.objects.order_by("pk"):
        seen_names[giver.name] += 1
        if seen_names[giver.name] > 1:
            n = seen_names[giver.name]
            # Find a free suffix; loop in the rare case "name 2" also collides
            while MissionGiver.objects.filter(name=f"{giver.name} {n}").exists():
                n += 1
            giver.name = f"{giver.name} {n}"
            giver.save(update_fields=["name"])
            seen_names[giver.name] = 1


def noop_reverse(apps, schema_editor):
    """Reverse is a no-op: re-introducing duplicates would require knowing the original collisions."""


class Migration(migrations.Migration):
    dependencies = [
        ("missions", "0005_drop_slug_fields"),
    ]

    operations = [
        migrations.RunPython(dedupe_giver_names, noop_reverse),
        migrations.AlterField(
            model_name="missiongiver",
            name="name",
            field=models.CharField(max_length=200, unique=True),
        ),
    ]
