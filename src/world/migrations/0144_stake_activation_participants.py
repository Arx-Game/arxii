from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("arxii", "0143_standing_visibility")]

    operations = [
        migrations.AddField(
            model_name="stakecontractactivation",
            name="participant_sheets",
            field=models.ManyToManyField(
                blank=True,
                help_text="Character sheets committed when this contract was activated.",
                related_name="stake_contract_activations",
                to="arxii.charactersheet",
            ),
        ),
    ]
