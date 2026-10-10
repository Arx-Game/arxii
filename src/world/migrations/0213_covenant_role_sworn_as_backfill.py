"""Every existing covenant vow was sworn under the character's primary face (#4208).

Data-only (a migration is schema-only or data-only): the column was added nullable
in 0212 and 0214 makes it required once every row carries a face. Rows already
carrying a face are left alone, so a re-run is safe. The PRIMARY persona is the
one `persona_type="primary"` row every sheet carries; a vow on a sheet without one
(the primary invariant broken) is left null and 0214's NOT NULL refuses the
converge loudly rather than inventing a face.
"""

from django.db import migrations

PRIMARY = "primary"


def forwards(apps, schema_editor):
    CharacterCovenantRole = apps.get_model("arxii", "CharacterCovenantRole")
    Persona = apps.get_model("arxii", "Persona")
    primaries = {
        sheet_id: persona_id
        for persona_id, sheet_id in Persona.objects.filter(persona_type=PRIMARY).values_list(
            "pk", "character_sheet_id"
        )
    }
    unsworn = CharacterCovenantRole.objects.filter(sworn_as__isnull=True).values_list(
        "pk", "character_sheet_id"
    )
    for row_id, sheet_id in unsworn:
        primary_id = primaries.get(sheet_id)
        if primary_id is not None:
            CharacterCovenantRole.objects.filter(pk=row_id).update(sworn_as_id=primary_id)


class Migration(migrations.Migration):
    dependencies = [("arxii", "0212_covenant_role_sworn_as")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
