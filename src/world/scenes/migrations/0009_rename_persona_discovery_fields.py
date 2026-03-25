from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("scenes", "0008_personadiscovery_persona_discovery_normalized_order"),
    ]

    operations = [
        # Drop constraints that reference old field names
        migrations.RemoveConstraint(
            model_name="personadiscovery",
            name="unique_persona_discovery",
        ),
        migrations.RemoveConstraint(
            model_name="personadiscovery",
            name="persona_discovery_normalized_order",
        ),
        # Rename fields
        migrations.RenameField(
            model_name="personadiscovery",
            old_name="persona_a",
            new_name="persona",
        ),
        migrations.RenameField(
            model_name="personadiscovery",
            old_name="persona_b",
            new_name="linked_to",
        ),
        # Update field definitions (help_text, related_name)
        migrations.AlterField(
            model_name="personadiscovery",
            name="persona",
            field=models.ForeignKey(
                help_text="The persona that was identified/encountered (lower PK for normalization)",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="discoveries_as_subject",
                to="scenes.persona",
            ),
        ),
        migrations.AlterField(
            model_name="personadiscovery",
            name="linked_to",
            field=models.ForeignKey(
                help_text="The persona they were discovered to be the same person as (higher PK)",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="discoveries_as_linked",
                to="scenes.persona",
            ),
        ),
        # Re-add constraints with new field names
        migrations.AddConstraint(
            model_name="personadiscovery",
            constraint=models.UniqueConstraint(
                fields=["persona", "linked_to", "discovered_by"],
                name="unique_persona_discovery",
            ),
        ),
        migrations.AddConstraint(
            model_name="personadiscovery",
            constraint=models.CheckConstraint(
                check=models.Q(("persona_id__lt", models.F("linked_to_id"))),
                name="persona_discovery_normalized_order",
            ),
        ),
    ]
