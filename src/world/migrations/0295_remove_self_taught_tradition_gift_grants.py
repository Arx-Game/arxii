"""Remove the self-taught Traditions' Gift grant rows (#4664, slice 1 of #4659).

Data only. A Tradition Gift Grant used to make a Gift pickable under its Tradition, so
the self-taught Tradition carried one row per Major Gift (17 on the newest production
dump) only to keep every Gift open to a self-taught character. Since #4659 any
Tradition may teach any Major Gift and a row means "a Gift this Tradition favors", so
those rows would wrongly mark every Gift as favored for every self-taught student.

Deleted: every grant row of a Tradition that some Beginning lists in the self-taught
state, when the row keeps no special techniques. A row with special techniques is kept,
since it still restricts those techniques to the Tradition. Self-taught is read from
`BeginningTradition.state`, never from a Tradition's name.

Disposition: deliberate discard, signed off by the maintainer in #4659 (Decision 9). The
rows carry no text; reversing does nothing, and they are recoverable from backup only.
"""

from django.db import migrations

SELF_TAUGHT = "self_taught"


def remove_self_taught_grants(apps, schema_editor):
    BeginningTradition = apps.get_model("arxii", "BeginningTradition")
    TraditionGiftGrant = apps.get_model("arxii", "TraditionGiftGrant")
    self_taught = BeginningTradition.objects.filter(state=SELF_TAUGHT).values_list(
        "tradition_id", flat=True
    )
    TraditionGiftGrant.objects.filter(
        tradition_id__in=self_taught, special_techniques__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0294_distinction_effect_rank_sizes"),
    ]

    operations = [
        migrations.RunPython(remove_self_taught_grants, migrations.RunPython.noop),
    ]
