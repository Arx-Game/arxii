# Character slots (#3996): roster-versus-original character is the entry's
# creation_provenance from here on. Carry the hand-set CharacterSheet.is_oc flag
# across before 0160 drops the column (data-only; the schema change is separate).

from django.db import migrations


def forwards(apps, schema_editor):
    RosterEntry = apps.get_model("arxii", "RosterEntry")
    RosterEntry.objects.filter(character_sheet__is_oc=True).update(
        creation_provenance="player",  # CreationProvenance.PLAYER's stored value
    )
    # Historical rows: before #3996 the two staff paths that mint an entry outside
    # character creation (a graduated NPC, a GM or staff character) left the
    # column default, PLAYER. An entry on the Available, Restricted or NPC shelf
    # is staff-authored by construction (an original character is frozen, never
    # returned to a shelf), so retag those; Active-shelf rows with a tenure are
    # left as they are, and staff can correct one in the admin.
    RosterEntry.objects.filter(
        roster__roster_type__in=["Available", "Restricted", "NPC"],
        creation_provenance="player",
    ).update(creation_provenance="staff")  # CreationProvenance.STAFF's stored value


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0158_playerdata_extra_character_slots"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
