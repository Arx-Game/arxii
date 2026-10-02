"""#4101 Task 1: DramaticMomentSuggestion -> GMPrompt (rename only, rows kept)."""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("arxii", "0178_technique_personalization_constraints")]

    operations = [
        migrations.RenameModel(old_name="DramaticMomentSuggestion", new_name="GMPrompt"),
        migrations.AlterModelOptions(
            name="gmprompt",
            options={
                "ordering": ["-created_at"],
                "verbose_name": "GM Prompt",
                "verbose_name_plural": "GM Prompts",
            },
        ),
        migrations.AlterField(
            model_name="gmprompt",
            name="character_sheet",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="gm_prompts",
                to="arxii.charactersheet",
            ),
        ),
        migrations.AlterField(
            model_name="gmprompt",
            name="scene",
            field=models.ForeignKey(
                blank=True,
                help_text="Scene context; nullable for resilience to scene cleanup.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="gm_prompts",
                to="arxii.scene",
            ),
        ),
        migrations.AlterField(
            model_name="gmprompt",
            name="interaction",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="The entrance pose that triggered this prompt; nullable.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="gm_prompts",
                to="arxii.interaction",
            ),
        ),
        migrations.AlterField(
            model_name="gmprompt",
            name="technique",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "The technique the entrance was cast with. Carried so that confirming "
                    "the suggestion can resolve the resonance from the thread the character "
                    "wove into that technique's gift. Null for a manual GM tag with no "
                    "technique behind it."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="gm_prompts",
                to="arxii.technique",
            ),
        ),
        migrations.AlterField(
            model_name="gmprompt",
            name="resolved_by",
            field=models.ForeignKey(
                blank=True,
                help_text="GM account that confirmed or dismissed this prompt.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="gm_prompts_resolved",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
