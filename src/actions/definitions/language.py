"""Language actions (#2993): sticky spoken-language switching + weekly training.

``SetLanguageAction`` flips the actor's sticky ``current_language`` (the
default a bare ``say`` speaks in) -- it never teaches, only requires the actor
already knows the tongue (fluency >= 1). ``TrainLanguageAction`` is the
weekly-gated dp-award session, mirroring ``TrainTechniqueAction``'s
teacher-vs-self-study split (`technique_training.py`) but against the
cumulative ``DevelopmentPoints``/``CharacterTraitValue`` fluency track instead
of a meter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.prerequisites import HasCharacterSheetPrerequisite, Prerequisite
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.species.models import Language

# PLACEHOLDER tuning values (#2993) -- Apostate's ratified defaults, pending a
# real balance pass once language training sees play.
TEACHER_DP_PER_SESSION = 15
SELF_STUDY_DP_PER_SESSION = 8


def _co_present_fluent_teacher(
    actor: ObjectDB, language: Language, teacher_id: int | None
) -> ObjectDB | None:
    """Resolve ``teacher_id`` to a co-present character FLUENT in ``language``.

    Silent fallback to ``None`` (self-study rates) whenever the teacher is
    unset, doesn't exist, isn't co-present, or isn't fluent -- never a hard
    block (mirrors ``_co_present_teacher``, `technique_training.py:44`).
    """
    if teacher_id is None:
        return None
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    teacher = ObjectDB.objects.filter(pk=teacher_id).first()
    if teacher is None or teacher.location != actor.location:
        return None
    try:
        teacher_sheet = teacher.sheet_data
    except ObjectDoesNotExist:
        return None

    from world.species.language_constants import FLUENT_GRANT_VALUE  # noqa: PLC0415
    from world.species.language_services import fluency_value  # noqa: PLC0415

    if fluency_value(teacher_sheet, language) < FLUENT_GRANT_VALUE:
        return None
    return teacher


@dataclass
class SetLanguageAction(Action):
    """Set (or reset) the actor's sticky spoken language.

    kwargs:
        language_id: pk of the ``Language`` to speak going forward, or
            ``None``/omitted to reset to the universal default. Requires the
            actor already knows the language (fluency >= 1) -- this action
            switches the sticky default, it never teaches.
    """

    key: str = "set_language"
    name: str = "Set Language"
    icon: str = "chat"
    category: str = "communication"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        language_id: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        sheet = actor.sheet_data

        if language_id is None:
            sheet.current_language = None
            sheet.save(update_fields=["current_language"])
            return ActionResult(success=True, message="You will now speak the universal tongue.")

        from world.species.language_services import fluency_value  # noqa: PLC0415
        from world.species.models import Language  # noqa: PLC0415

        language = Language.objects.filter(pk=language_id).first()
        if language is None or fluency_value(sheet, language) < 1:
            return ActionResult(success=False, message="You don't know that tongue.")

        sheet.current_language = language
        sheet.save(update_fields=["current_language"])
        return ActionResult(success=True, message=f"You will now speak {language.name}.")


@dataclass
class TrainLanguageAction(Action):
    """Run one weekly language-training session.

    kwargs:
        language_id: pk of the ``Language`` to train (required).
        teacher_id: optional pk of a co-located character whose sheet is
            FLUENT in the language. Absent/not co-present/not fluent silently
            falls back to self-study rates -- never a hard block (mirrors
            ``TrainTechniqueAction``'s teacher resolution).
    """

    key: str = "train_language"
    name: str = "Train Language"
    icon: str = "book"
    category: str = "communication"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        language_id: int,
        teacher_id: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415
        from world.progression.models.rewards import (  # noqa: PLC0415
            DevelopmentPoints,
            DevelopmentTransaction,
        )
        from world.progression.types import DevelopmentSource, ProgressionReason  # noqa: PLC0415
        from world.species.models import Language  # noqa: PLC0415

        language = Language.objects.filter(pk=language_id).first()
        if language is None:
            return ActionResult(success=False, message="There is no such language.")
        if language.trait_id is None:
            return ActionResult(
                success=False,
                message=f"{language.name} has no trainable fluency track.",
            )

        sheet = actor.sheet_data
        game_week = get_current_game_week()

        already_trained = DevelopmentTransaction.objects.filter(
            character_sheet=sheet,
            trait=language.trait,
            source__in=(DevelopmentSource.TRAINING, DevelopmentSource.PRACTICE),
            game_week=game_week,
        ).exists()
        if already_trained:
            return ActionResult(
                success=False,
                message=f"You've already studied {language.name} this week.",
            )

        teacher = _co_present_fluent_teacher(actor, language, teacher_id)
        if teacher is not None:
            amount = TEACHER_DP_PER_SESSION
            source = DevelopmentSource.TRAINING
        else:
            amount = SELF_STUDY_DP_PER_SESSION
            source = DevelopmentSource.PRACTICE

        dev_tracker, _created = DevelopmentPoints.objects.get_or_create(
            character_sheet=sheet, trait=language.trait
        )
        level_ups = dev_tracker.award_points(amount)

        DevelopmentTransaction.objects.create(
            character_sheet=sheet,
            trait=language.trait,
            source=source,
            amount=amount,
            reason=ProgressionReason.SYSTEM_AWARD,
            game_week=game_week,
            description=f"Language training: {amount} dp for {language.name}",
        )

        mode = "with a teacher" if teacher is not None else "through self-study"
        message = f"You study {language.name} {mode}, gaining {amount} development points."
        if level_ups:
            _old_level, new_level = level_ups[-1]
            message += f" Your fluency deepens to {new_level}."

        return ActionResult(
            success=True,
            message=message,
            data={
                "language_id": language.pk,
                "amount": amount,
                "self_study": teacher is None,
                "level_ups": level_ups,
            },
        )
