"""Delete the life-stage paragraph rows before their column is dropped (#5178).

Data only. A ``CharacterOriginSlot`` row with ``life_stage`` set held the paragraph a
player wrote for one stage of the life (#4872). Finalize also printed that paragraph into
the character's ``Profile.background``, which this migration does not touch, so the text
survives there. The rows are play state, not authored content. The next migration drops
the column and restores the check that a row names a prompt or a beat, which these rows
would fail.
"""

from django.db import migrations


def delete_stage_rows(apps, schema_editor):
    CharacterOriginSlot = apps.get_model("arxii", "CharacterOriginSlot")
    CharacterOriginSlot.objects.exclude(life_stage="").delete()


class Migration(migrations.Migration):
    dependencies = [("arxii", "0449_delete_atonement_rite_ritual")]

    operations = [
        migrations.RunPython(delete_stage_rows, migrations.RunPython.noop),
    ]
