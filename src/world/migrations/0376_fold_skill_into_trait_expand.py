"""Fold Skill into Trait, step 1 of 3: expand (schema only, #5008 slice 3, ADR-0237).

A skill becomes a skill-type Trait. This step only adds columns:

* ``Trait.tooltip``, ``Trait.display_order`` and ``Trait.is_active``, the three fields
  that lived on ``Skill``.
* ``Trait.skill_fold_had_row``, a temporary marker the copy step sets on each trait that
  had a ``Skill`` row, so its reverse recreates exactly those rows. The contract step
  drops it.
* Beside every FK to ``Skill``, a nullable FK to ``Trait`` under a temporary
  ``<name>_fold`` name. The contract step drops the old FK and renames this one into
  its place.

The old non-null FKs become nullable here, and the training allocation's skill-xor-
specialization check is dropped here, so the contract step's reverse can recreate the
old columns empty and the copy step's reverse can fill them (the check comes back on
the new column in the contract step, and on the old one if this step is reversed).
"""

from django.db import migrations, models
import django.db.models.deletion

# The three Trait fields carry a database default too, so the release still running
# between migrate and the Server reload can INSERT a Trait without naming them.
_SKILL = "arxii.skill"
_TRAIT = "arxii.trait"
_CASCADE = django.db.models.deletion.CASCADE
_PROTECT = django.db.models.deletion.PROTECT
_SET_NULL = django.db.models.deletion.SET_NULL
# CombatStyle.skill is a OneToOne (one style per skill); the others are plain FKs.
_ONE_TO_ONE_MODEL = "combatstyle"

# (model, old field name, on_delete) for every FK to Skill; CombatStyle's is a OneToOne.
_SKILL_FKS = (
    ("specialization", "parent_skill", _CASCADE),
    ("skillpointbudget", "teaching_skill", _SET_NULL),
    ("pathskillsuggestion", "skill", _CASCADE),
    ("trainingallocation", "skill", _CASCADE),
    ("npcpresetskillline", "skill", _PROTECT),
    ("legendspread", "skill", _SET_NULL),
    ("techniquestyle", "skill", _SET_NULL),
    ("technique", "skill", _SET_NULL),
    ("magicactivityskill", "skill", _PROTECT),
    ("ritualcheckconfig", "skill", _PROTECT),
    ("combatstyle", "skill", _PROTECT),
    ("skillcourseofferdetails", "skill", _PROTECT),
    ("sceneactionrequest", "snapshot_skill", _SET_NULL),
)

# The old FKs that are NOT NULL today, with their related names.
_NON_NULL_OLD_FKS = (
    ("specialization", "parent_skill", _CASCADE, "specializations"),
    ("pathskillsuggestion", "skill", _CASCADE, "path_suggestions"),
    ("npcpresetskillline", "skill", _PROTECT, "npc_preset_skill_lines"),
    ("magicactivityskill", "skill", _PROTECT, "magic_activity_rows"),
    ("ritualcheckconfig", "skill", _PROTECT, "+"),
    ("skillcourseofferdetails", "skill", _PROTECT, "course_offers"),
)


def _temp_fk(model_name: str, on_delete) -> models.Field:
    field_class = models.OneToOneField if model_name == _ONE_TO_ONE_MODEL else models.ForeignKey
    return field_class(
        blank=True,
        null=True,
        on_delete=on_delete,
        related_name="+",
        to=_TRAIT,
        help_text="Temporary column for the Skill-into-Trait fold (#5008).",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0375_one_skill_rating_store"),
    ]

    operations = [
        migrations.AddField(
            model_name="trait",
            name="tooltip",
            field=models.TextField(
                blank=True, db_default="", help_text="Short description shown on hover in UI"
            ),
        ),
        migrations.AddField(
            model_name="trait",
            name="display_order",
            field=models.PositiveSmallIntegerField(
                db_default=0, default=0, help_text="Order for display in character sheets and CG"
            ),
        ),
        migrations.AddField(
            model_name="trait",
            name="is_active",
            field=models.BooleanField(
                db_default=True,
                default=True,
                help_text=(
                    "Whether this trait is available for use. An inactive skill is left out "
                    "of character creation, training and the sheet's pickers."
                ),
            ),
        ),
        migrations.AddField(
            model_name="trait",
            name="skill_fold_had_row",
            field=models.BooleanField(
                default=False,
                help_text="Temporary marker for the Skill-into-Trait fold (#5008).",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="trainingallocation",
            name="training_skill_xor_specialization",
        ),
        *(
            migrations.AlterField(
                model_name=model_name,
                name=field_name,
                field=models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=on_delete,
                    related_name=related_name,
                    to=_SKILL,
                ),
            )
            for model_name, field_name, on_delete, related_name in _NON_NULL_OLD_FKS
        ),
        *(
            migrations.AddField(
                model_name=model_name,
                name=f"{field_name}_fold",
                field=_temp_fk(model_name, on_delete),
            )
            for model_name, field_name, on_delete in _SKILL_FKS
        ),
    ]
