# Generated manually for PrerequisiteType → Prerequisite rename + new fields

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("mechanics", "0001_initial"),
        ("objects", "0013_defaultobject_alter_objectdb_id_defaultcharacter_and_more"),
    ]

    operations = [
        # Step 1: Rename the model (Django handles FK references automatically)
        migrations.RenameModel(
            old_name="PrerequisiteType",
            new_name="Prerequisite",
        ),
        # Step 2: Add new fields to Prerequisite
        migrations.AddField(
            model_name="prerequisite",
            name="property",
            field=models.ForeignKey(
                help_text="The property to check for on the target entity.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="prerequisites",
                to="mechanics.property",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="prerequisite",
            name="property_holder",
            field=models.CharField(
                choices=[
                    ("self", "Character (self)"),
                    ("target", "Target object"),
                    ("location", "Location (room)"),
                ],
                help_text="Which entity to check: character, target object, or location.",
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="prerequisite",
            name="minimum_value",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Minimum property value required. 1 = property must be present.",
            ),
        ),
        # Step 3: Add target_object FK to ChallengeInstance
        migrations.AddField(
            model_name="challengeinstance",
            name="target_object",
            field=models.ForeignKey(
                help_text="The object embodying this challenge in the world.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="challenge_target_instances",
                to="objects.objectdb",
            ),
            preserve_default=False,
        ),
    ]
