# Character slots (#3996): roster-versus-original character is the entry's
# creation_provenance from here on. Carry the hand-set CharacterSheet.is_oc flag
# across before 0160 drops the column (data-only; the schema change is separate).

from django.db import migrations


def forwards(apps, schema_editor):
    RosterEntry = apps.get_model("arxii", "RosterEntry")
    RosterEntry.objects.filter(character_sheet__is_oc=True).update(
        creation_provenance="PLAYER",  # CreationProvenance.PLAYER
    )


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0158_playerdata_extra_character_slots"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
