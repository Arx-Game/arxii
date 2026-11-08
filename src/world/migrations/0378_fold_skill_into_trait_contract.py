"""Fold Skill into Trait, step 3 of 3: contract (schema only, #5008 slice 3, ADR-0237).

The copy step has pointed every temporary ``<name>_fold`` FK at the trait the old FK's
skill sat on. This step drops the old FKs (and the constraints that name them), renames
drops the temporary marker on ``Trait`` and deletes the ``Skill`` table. ``Skill`` comes
back as a proxy of ``Trait`` (#5015): the same name, no table. Each temporary FK is
renamed to the old field name and given its final definition, pointing at the proxy
(``Specialization.parent_skill`` is non-null again, with its ``(parent_skill, name)``
unique key back). Pointing a FK at the proxy is state only: the column still holds a
``Trait`` pk.

Reverse: drops the proxy, recreates the ``Skill`` table and the old columns empty (and
nullable, as the expand step left them); reversing the copy step then repopulates them.
"""

from django.db import migrations, models
import django.db.models.deletion

# (model, field name) of every FK that pointed at Skill.
_SKILL_FKS = (
    ("specialization", "parent_skill"),
    ("skillpointbudget", "teaching_skill"),
    ("pathskillsuggestion", "skill"),
    ("trainingallocation", "skill"),
    ("npcpresetskillline", "skill"),
    ("legendspread", "skill"),
    ("techniquestyle", "skill"),
    ("technique", "skill"),
    ("magicactivityskill", "skill"),
    ("ritualcheckconfig", "skill"),
    ("combatstyle", "skill"),
    ("skillcourseofferdetails", "skill"),
    ("sceneactionrequest", "snapshot_skill"),
)


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0377_fold_skill_into_trait_copy"),
    ]

    operations = [
        # Constraints naming an old FK go first, so the old column can be dropped.
        migrations.AlterUniqueTogether(name="specialization", unique_together=set()),
        migrations.AlterUniqueTogether(name="pathskillsuggestion", unique_together=set()),
        migrations.AlterUniqueTogether(
            name="trainingallocation", unique_together={("character", "specialization")}
        ),
        migrations.RemoveConstraint(
            model_name="npcpresetskillline", name="roster_npc_preset_skill_unique"
        ),
        migrations.RemoveConstraint(
            model_name="magicactivityskill", name="unique_magic_activity_skill"
        ),
        *(
            migrations.RemoveField(model_name=model_name, name=field_name)
            for model_name, field_name in _SKILL_FKS
        ),
        migrations.RemoveField(model_name="trait", name="skill_fold_had_row"),
        migrations.DeleteModel(name="Skill"),
        # Skill comes back as a proxy of Trait (#5015): a typed view, no table.
        migrations.CreateModel(
            name="Skill",
            fields=[],
            options={"proxy": True, "indexes": [], "constraints": []},
            bases=("arxii.trait",),
        ),
        *(
            migrations.RenameField(
                model_name=model_name, old_name=f"{field_name}_fold", new_name=field_name
            )
            for model_name, field_name in _SKILL_FKS
        ),
        migrations.AlterField(
            model_name="specialization",
            name="parent_skill",
            field=models.ForeignKey(
                help_text="The parent skill this specialization belongs to",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="specializations",
                to="arxii.skill",
            ),
        ),
        migrations.AlterField(
            model_name="skillpointbudget",
            name="teaching_skill",
            field=models.ForeignKey(
                blank=True,
                help_text="Skill used for mentor teaching bonus in training formula",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="arxii.skill",
            ),
        ),
        migrations.AlterField(
            model_name="pathskillsuggestion",
            name="skill",
            field=models.ForeignKey(
                help_text="The skill being suggested",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="path_suggestions",
                to="arxii.skill",
            ),
        ),
        migrations.AlterField(
            model_name="trainingallocation",
            name="skill",
            field=models.ForeignKey(
                blank=True,
                help_text="The skill being trained (mutually exclusive with specialization)",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="training_allocations",
                to="arxii.skill",
            ),
        ),
        migrations.AlterField(
            model_name="npcpresetskillline",
            name="skill",
            field=models.ForeignKey(
                help_text="PROTECT: mirrors NPCPresetTraitLine.trait's rationale.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="npc_preset_skill_lines",
                to="arxii.skill",
            ),
        ),
        migrations.AlterField(
            model_name="legendspread",
            name="skill",
            field=models.ForeignKey(
                blank=True,
                help_text="The skill used for this spread, if any",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="legend_spreads",
                to="arxii.skill",
            ),
        ),
        migrations.AlterField(
            model_name="techniquestyle",
            name="skill",
            field=models.ForeignKey(
                blank=True,
                error_messages={
                    "invalid": "Choose a skill in the Magic category that is not a combat style's skill. A magical roll adds only skills made for magic, so it never counts a skill a character picks elsewhere."
                },
                help_text="The skill every cast worked in this style adds (#5002): a Path's casts take the Path style's skill, a Gift with its own style takes that style's. A technique's own skill, if set, wins. Blank = casts in this style add no skill. Magic-category skills only, never a combat style's skill.",
                limit_choices_to=models.Q(("category", "magic"), ("combat_style__isnull", True)),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="technique_styles",
                to="arxii.skill",
            ),
        ),
        migrations.AlterField(
            model_name="technique",
            name="skill",
            field=models.ForeignKey(
                blank=True,
                error_messages={
                    "invalid": "Choose a skill in the Magic category that is not a combat style's skill. A magical roll adds only skills made for magic, so it never counts a skill a character picks elsewhere."
                },
                help_text="Overrides the cast skill for this one technique (#4450). Blank = use the skill of the style the cast is worked in: the Gift's own style if it sets one, else the caster's Path style (#5002). Magic-category skills only, never a combat style's skill.",
                limit_choices_to=models.Q(("category", "magic"), ("combat_style__isnull", True)),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="override_techniques",
                to="arxii.skill",
            ),
        ),
        migrations.AlterField(
            model_name="magicactivityskill",
            name="skill",
            field=models.ForeignKey(
                error_messages={
                    "invalid": "Choose a skill in the Magic category that is not a combat style's skill. A magical roll adds only skills made for magic, so it never counts a skill a character picks elsewhere."
                },
                help_text="The skill added to every roll of this activity. Magic-category skills only, never a combat style's skill.",
                limit_choices_to=models.Q(("category", "magic"), ("combat_style__isnull", True)),
                on_delete=django.db.models.deletion.PROTECT,
                related_name="magic_activity_rows",
                to="arxii.skill",
            ),
        ),
        migrations.AlterField(
            model_name="ritualcheckconfig",
            name="skill",
            field=models.ForeignKey(
                help_text="The skill used in this ritual's check.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="arxii.skill",
            ),
        ),
        migrations.AlterField(
            model_name="combatstyle",
            name="skill",
            field=models.OneToOneField(
                blank=True,
                error_messages={
                    "invalid": "Choose a skill in the Magic category. A magical roll adds only skills made for magic, so it never counts a skill a character picks elsewhere."
                },
                help_text="The style's own skill, added to Strike, technique hit and defense rolls while the character fights this style's way. One style per skill. Magic-category skills only.",
                limit_choices_to=models.Q(("category", "magic")),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="combat_style",
                to="arxii.skill",
            ),
        ),
        migrations.AlterField(
            model_name="skillcourseofferdetails",
            name="skill",
            field=models.ForeignKey(
                help_text="The skill this course develops.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="course_offers",
                to="arxii.skill",
            ),
        ),
        migrations.AlterField(
            model_name="sceneactionrequest",
            name="snapshot_skill",
            field=models.ForeignKey(
                blank=True,
                help_text="Skill from ritual check spec at fire time",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="arxii.skill",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="specialization", unique_together={("parent_skill", "name")}
        ),
        migrations.AlterUniqueTogether(
            name="pathskillsuggestion", unique_together={("character_path", "skill")}
        ),
        migrations.AlterUniqueTogether(
            name="trainingallocation",
            unique_together={("character", "skill"), ("character", "specialization")},
        ),
        migrations.AddConstraint(
            model_name="trainingallocation",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("skill__isnull", False), ("specialization__isnull", True)),
                    models.Q(("skill__isnull", True), ("specialization__isnull", False)),
                    _connector="OR",
                ),
                name="training_skill_xor_specialization",
            ),
        ),
        migrations.AddConstraint(
            model_name="npcpresetskillline",
            constraint=models.UniqueConstraint(
                fields=("preset", "skill"), name="roster_npc_preset_skill_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="magicactivityskill",
            constraint=models.UniqueConstraint(
                fields=("activity", "skill"), name="unique_magic_activity_skill"
            ),
        ),
        migrations.AlterModelOptions(
            name="pathskillsuggestion",
            options={"ordering": ["character_path", "display_order", "skill__name"]},
        ),
    ]
