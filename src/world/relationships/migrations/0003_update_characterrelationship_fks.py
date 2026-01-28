# Update CharacterRelationship FKs from ObjectDB to CharacterSheet

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Update CharacterRelationship FKs from ObjectDB to CharacterSheet.

    Scopes relationships to tracked characters (PCs and NPCs with sheets)
    rather than all game objects.
    Data was cleared in the previous migration.
    """

    dependencies = [
        ("character_sheets", "0001_initial"),
        ("relationships", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="characterrelationship",
            name="source",
            field=models.ForeignKey(
                help_text="The character who holds this opinion",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="relationships_as_source",
                to="character_sheets.charactersheet",
            ),
        ),
        migrations.AlterField(
            model_name="characterrelationship",
            name="target",
            field=models.ForeignKey(
                help_text="The character this opinion is about",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="relationships_as_target",
                to="character_sheets.charactersheet",
            ),
        ),
    ]
