"""Data only (#4361): carry live standoff state onto the new snapshot columns.

Play state, so nothing authored is at risk. Two things move:

- ``StandoffReveal.drive_property`` takes the property of the ``CreatureDrive`` each drive
  reveal points at, so the next migration can drop the old ``drive`` column.
- Opponents in an encounter with a live standoff group (open or proposed) get the
  standoff profile they used to read live from their creature template: ``cause`` and
  ``cause_margin_percent`` copied, and each template drive stamped as an
  ``ObjectProperty`` on the opponent's object. Opponents outside a live standoff are not
  touched: their profile is only read while a standoff is open.

Reverse: drive reveals get their ``CreatureDrive`` back by (template, property); the
opponent columns are left as they are (the previous schema never reads them) and the
stamped ``ObjectProperty`` rows are left in place.
"""

from django.db import migrations

_LIVE_STATES = ("open", "proposed")
_DRIVE = "drive"


def forward(apps, schema_editor):
    StandoffReveal = apps.get_model("arxii", "StandoffReveal")
    StandoffGroup = apps.get_model("arxii", "StandoffGroup")
    CombatOpponent = apps.get_model("arxii", "CombatOpponent")
    CreatureDrive = apps.get_model("arxii", "CreatureDrive")
    ObjectProperty = apps.get_model("arxii", "ObjectProperty")

    for reveal in StandoffReveal.objects.filter(kind=_DRIVE, drive__isnull=False).select_related(
        "drive"
    ):
        reveal.drive_property_id = reveal.drive.property_id
        reveal.save(update_fields=["drive_property"])

    encounter_ids = set(
        StandoffGroup.objects.filter(state__in=_LIVE_STATES).values_list("encounter_id", flat=True)
    )
    opponents = CombatOpponent.objects.filter(
        encounter_id__in=encounter_ids, creature_template__isnull=False
    ).select_related("creature_template")
    for opponent in opponents:
        template = opponent.creature_template
        opponent.cause = template.cause
        opponent.cause_margin_percent = template.cause_margin_percent
        opponent.save(update_fields=["cause", "cause_margin_percent"])
        if opponent.objectdb_id is None:
            continue
        for drive in CreatureDrive.objects.filter(creature_template=template):
            ObjectProperty.objects.update_or_create(
                object_id=opponent.objectdb_id,
                property_id=drive.property_id,
                defaults={"value": drive.strength},
            )


def reverse(apps, schema_editor):
    StandoffReveal = apps.get_model("arxii", "StandoffReveal")
    CreatureDrive = apps.get_model("arxii", "CreatureDrive")

    for reveal in StandoffReveal.objects.filter(
        kind=_DRIVE, drive_property__isnull=False
    ).select_related("group"):
        drive = CreatureDrive.objects.filter(
            creature_template_id=reveal.group.creature_template_id,
            property_id=reveal.drive_property_id,
        ).first()
        if drive is None:
            # A drive the placement added has no template row to point back at.
            reveal.delete()
            continue
        reveal.drive_id = drive.pk
        reveal.save(update_fields=["drive"])


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0230_placement_edits_and_inherited_faction_rules"),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
