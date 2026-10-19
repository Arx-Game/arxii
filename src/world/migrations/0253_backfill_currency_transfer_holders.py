"""Snapshot each existing CurrencyTransfer's holders (#4467).

Data only. The columns came in 0252; the constraint that reads them follows in
0254, because a constraint added in the same transaction as the backfill would
queue trigger events against the rows just written.

A side whose purse or treasury is still there gets its kind and its name today
(a character's primary persona name, an organization's name). A side that is
already null stays blank: those rows are the ones the old constraint could not
have let a delete null, and the holder they once named is not recoverable.
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
        purse_id: sheet_names.get(sheet_id, "")
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
            CurrencyTransfer.objects.filter(**{f"{side}_{fk}__isnull": False}).update(
                **{
                    f"{side}_holder_kind": fk,
                    f"{side}_holder_name": Case(
                        *whens, default=Value(""), output_field=CharField()
                    ),
                }
            )


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0252_currency_transfer_holder_snapshot"),
    ]

    operations = [
        migrations.RunPython(snapshot_holders, migrations.RunPython.noop),
    ]
