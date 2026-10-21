"""Snapshot the holders of every CurrencyTransfer the previous release wrote (#4467).

Data only, and the same backfill as 0254 narrowed to sides whose kind is still blank.
The release that shipped 0254 also wrote rows with the old code between the migration
and the release swap: purse or treasury set, no snapshot. Those rows would fail the
constraint 0271 puts on the kinds (and could not survive their holder's deletion), so
every one is snapshotted here first. Rows that already carry a kind are left alone.
"""

from django.db import migrations
from django.db.models import Case, CharField, Value, When

PRIMARY_PERSONA = "primary"


def snapshot_holders(apps, schema_editor):
    CurrencyTransfer = apps.get_model("arxii", "CurrencyTransfer")
    CharacterPurse = apps.get_model("arxii", "CharacterPurse")
    OrganizationTreasury = apps.get_model("arxii", "OrganizationTreasury")
    Persona = apps.get_model("arxii", "Persona")

    sheet_names = dict(
        Persona.objects.filter(persona_type=PRIMARY_PERSONA).values_list(
            "character_sheet_id", "name"
        )
    )
    purse_names = {
        purse_id: sheet_names.get(sheet_id, f"Character {sheet_id}")
        for purse_id, sheet_id in CharacterPurse.objects.values_list("pk", "character_sheet_id")
    }
    treasury_names = dict(OrganizationTreasury.objects.values_list("pk", "organization__name"))

    for side in ("from", "to"):
        for fk, names in (("purse", purse_names), ("treasury", treasury_names)):
            whens = [
                When(**{f"{side}_{fk}_id": holder_id}, then=Value(name))
                for holder_id, name in names.items()
            ]
            if not whens:
                continue
            CurrencyTransfer.objects.filter(
                **{f"{side}_{fk}__isnull": False, f"{side}_holder_kind": ""}
            ).update(
                **{
                    f"{side}_holder_kind": fk,
                    f"{side}_holder_name": Case(
                        *whens, default=Value(""), output_field=CharField()
                    ),
                }
            )


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0269_worn_pieces_count_with_beings"),
    ]

    operations = [
        migrations.RunPython(snapshot_holders, migrations.RunPython.noop),
    ]
