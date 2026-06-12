from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("magic", "0017_auderemajorathreshold_auderemajoracrossing_and_more"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="RitualSceneActionConfig",
            new_name="RitualCheckConfig",
        ),
        migrations.AlterModelOptions(
            name="ritualcheckconfig",
            options={
                "verbose_name": "Ritual Check Config",
                "verbose_name_plural": "Ritual Check Configs",
            },
        ),
        migrations.AlterField(
            model_name="ritualcheckconfig",
            name="ritual",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="check_config",
                to="magic.ritual",
            ),
        ),
        migrations.AddField(
            model_name="ritualcheckconfig",
            name="non_founder_target_difficulty",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                help_text=(
                    "Authored difficulty when the actor lacks founder standing for the "
                    "target (e.g. a non-founder dissolving a Sanctum). NULL = no distinction."
                ),
            ),
        ),
    ]
