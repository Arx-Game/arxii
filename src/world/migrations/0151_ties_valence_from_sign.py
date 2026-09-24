"""Copy RelationshipType.sign onto the new valence axis before 0152 drops sign (#3957).

positive -> warm, negative -> hostile; anything else (there is no other authored
value today) is left at the field's own default, neutral.
"""

from django.db import migrations

_SIGN_TO_VALENCE = {
    "positive": "warm",
    "negative": "hostile",
}


def copy_sign_to_valence(apps, schema_editor):
    """Derive every RelationshipType row's valence from its about-to-be-dropped sign."""
    RelationshipType = apps.get_model("arxii", "RelationshipType")

    for sign, valence in _SIGN_TO_VALENCE.items():
        RelationshipType.objects.filter(sign=sign).update(valence=valence)


def noop_reverse(apps, schema_editor):
    """The reverse of a derived-field copy is a no-op; sign still holds the source value."""


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0150_ties_redrawn"),
    ]

    operations = [
        migrations.RunPython(copy_sign_to_valence, noop_reverse),
    ]
