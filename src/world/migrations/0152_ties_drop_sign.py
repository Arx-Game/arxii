"""Drop RelationshipType.sign now that 0151 has copied it onto valence (#3957)."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0151_ties_valence_from_sign"),
    ]

    operations = [
        migrations.RemoveField(model_name="relationshiptype", name="sign"),
    ]
