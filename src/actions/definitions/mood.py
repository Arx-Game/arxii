"""Mood actions (#2994): declared internal state + earned detection.

``SetMoodAction`` (telnet verb ``feel``) flips the actor's sticky ``current_mood`` --
mirrors ``SetLanguageAction`` (``language.py``) exactly, including its silence: it
returns only a self-facing ``ActionResult.message``, never calls
``message_location``/``record_interaction``, so there is no room echo and no scene
Interaction row. Per the ratified spec amendments, mood is INTERNAL by design -- the
draft's outward "Demeanor"/look-composition rendering was dropped entirely.

``SenseMoodAction`` (telnet verb ``sense_mood``... actually see ``commands/mood.py``)
is the sole way another character learns a mood: gated on the actor holding an
Empathy skill SPECIALIZATION (no thematically-right parent skill exists in the
catalog yet -- flagged, not force-fit, per the skill-list-is-provisional convention)
and resolved through ``perform_check`` (never flat probability). Success reveals the
target's current mood privately to the senser; the target is never notified either
way (SILENT).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory, TargetKind
from actions.prerequisites import (
    NO_ACTIVE_CHARACTER_MESSAGE,
    HasCharacterSheetPrerequisite,
    Prerequisite,
    resolve_actor_sheet,
)
from actions.types import ActionResult, TargetFilters, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext

# PLACEHOLDER content-authoring seam (#2994): no "Empathy" Specialization or its
# parent Skill exist in the catalog yet, and no "Sense Mood" CheckType composition
# exists either -- both are content (lore-repo authored), not code. Both gates below
# fail cleanly, rather than crashing, until that content lands.
MOOD_SENSE_SPECIALIZATION_NAME = "Empathy"
MOOD_SENSE_CHECK_TYPE_NAME = "Sense Mood"
MOOD_SENSE_TARGET_DIFFICULTY = 20  # PLACEHOLDER magnitude, pending a real balance pass.

_NO_TARGET_MESSAGE = "Sense whose mood?"
_NOT_PRESENT_MESSAGE = "They aren't here."
_NO_SHEET_MESSAGE = "There's no one there to read."
_NO_EMPATHY_MESSAGE = "You lack the empathy to read others."
_NO_CHECK_TYPE_MESSAGE = "You reach for the feeling, but the sense isn't yours to draw on yet."
_MISS_MESSAGE = "You can't get a read on them right now."
_SETTLED_MESSAGE = "You sense that {name}'s feelings are settled."
_SENSED_MESSAGE = "You sense that {name} feels {mood}."


@dataclass
class SetMoodAction(Action):
    """Set (or clear) the actor's sticky declared mood.

    kwargs:
        mood_id: pk of the ``MoodOption`` to declare, or ``None``/omitted to clear
            the declaration. Requires the option be ``is_active``. INTERNAL and
            SILENT -- message only to self, no room echo, no recorded Interaction.
    """

    key: str = "set_mood"
    name: str = "Set Mood"
    icon: str = "heart"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        mood_id: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        sheet = actor.sheet_data

        if mood_id is None:
            sheet.current_mood = None
            sheet.save(update_fields=["current_mood"])
            return ActionResult(success=True, message="Your feelings settle.")

        from world.character_sheets.models import MoodOption  # noqa: PLC0415

        mood = MoodOption.objects.filter(pk=mood_id, is_active=True).first()
        if mood is None:
            return ActionResult(success=False, message="There is no such mood.")

        sheet.current_mood = mood
        sheet.save(update_fields=["current_mood"])
        return ActionResult(success=True, message=f"You feel {mood.name.lower()}.")


def _resolve_mood_sense_target(kwargs: dict[str, Any]) -> ObjectDB | None:
    """Resolve the sense-mood target from any dispatch shape (mirrors
    ``identification._resolve_identify_target``): a resolved ``ObjectDB`` (telnet),
    or a ``Persona`` pk under ``target``/``target_persona_id`` (web REGISTRY dispatch).
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    target = kwargs.get("target")
    if isinstance(target, ObjectDB):
        return target
    if target is not None:
        return _resolve_persona_pk_to_character(target)

    persona_id = kwargs.get("target_persona_id")
    if persona_id is None:
        return None
    return _resolve_persona_pk_to_character(persona_id)


def _resolve_persona_pk_to_character(persona_id: Any) -> ObjectDB | None:
    from world.scenes.models import Persona  # noqa: PLC0415

    persona = Persona.objects.filter(pk=persona_id).select_related("character_sheet").first()
    if persona is None:
        return None
    return persona.character_sheet.character


@dataclass
class SenseMoodTargetPrerequisite(Prerequisite):
    """The sense-mood target must resolve, be co-located, and hold a CharacterSheet."""

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        del target
        kwargs = (context or {}).get("kwargs", {})
        target_obj = _resolve_mood_sense_target(kwargs)
        if target_obj is None:
            return False, _NO_TARGET_MESSAGE
        if target_obj.location != actor.location:
            return False, _NOT_PRESENT_MESSAGE
        if resolve_actor_sheet(target_obj) is None:
            return False, _NO_SHEET_MESSAGE
        return True, ""


@dataclass
class HasEmpathySpecializationPrerequisite(Prerequisite):
    """Actor must hold the Empathy specialization (value >= 1) -- the earned
    mood-detection gate (spec amendment 4: "detection is earned, not ambient").

    No thematically-right parent Skill for "Empathy" exists in the catalog yet (the
    skill list is provisional -- force-fitting an unrelated parent would be worse
    than flagging the hole). This gates on a ``Specialization`` named "Empathy"
    under ANY parent skill, so authoring the right parent skill later (content, not
    code) is all that's needed to make this reachable; a future technique/effect can
    grant the same read without holding the specialization at all (the seam the spec
    calls for) by attaching its own prerequisite/bypass rather than editing this one.
    """

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        del target, context
        sheet = resolve_actor_sheet(actor)
        if sheet is None:
            return False, NO_ACTIVE_CHARACTER_MESSAGE

        from world.skills.models import CharacterSpecializationValue  # noqa: PLC0415

        has_empathy = CharacterSpecializationValue.objects.filter(
            character=sheet,
            specialization__name__iexact=MOOD_SENSE_SPECIALIZATION_NAME,
            value__gte=1,
        ).exists()
        if not has_empathy:
            return False, _NO_EMPATHY_MESSAGE
        return True, ""


def _resolve_sense_mood_check(actor_sheet: Any) -> tuple[Any, Any] | ActionResult:
    """Resolve the actor's Empathy ``Specialization`` + the ``CheckType`` to roll.

    Returns ``(specialization, check_type)`` on success, or a failure
    ``ActionResult`` when either content row is missing -- both are content gaps
    flagged for later authoring (see module docstring), never a hard crash.
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.skills.models import CharacterSpecializationValue  # noqa: PLC0415

    specialization_value = (
        CharacterSpecializationValue.objects.filter(
            character=actor_sheet,
            specialization__name__iexact=MOOD_SENSE_SPECIALIZATION_NAME,
            value__gte=1,
        )
        .select_related("specialization")
        .first()
    )
    if specialization_value is None:
        # Defense-in-depth -- the prerequisite already gates this (mirrors the
        # double-guard idiom in identification.py).
        return ActionResult(success=False, message=_NO_EMPATHY_MESSAGE)

    check_type = CheckType.objects.filter(name=MOOD_SENSE_CHECK_TYPE_NAME).first()
    if check_type is None:
        return ActionResult(success=False, message=_NO_CHECK_TYPE_MESSAGE)

    return specialization_value.specialization, check_type


@dataclass
class SenseMoodAction(Action):
    """Try to privately read a co-located character's declared mood (#2994).

    Gated on the Empathy specialization (``HasEmpathySpecializationPrerequisite``);
    resolved via ``perform_check`` against ``MOOD_SENSE_TARGET_DIFFICULTY``. SILENT
    to the target in every outcome -- only the actor ever sees a message.
    """

    key: str = "sense_mood"
    name: str = "Sense Mood"
    icon: str = "heart"
    category: str = "social"
    target_type: TargetType = TargetType.SINGLE
    target_kind: TargetKind | None = TargetKind.PERSONA
    target_filters: TargetFilters | None = field(
        default_factory=lambda: TargetFilters(in_same_scene=True, exclude_self=True)
    )
    action_category: ActionCategory | None = ActionCategory.MENTAL

    def get_prerequisites(self) -> list[Prerequisite]:
        return [
            HasCharacterSheetPrerequisite(),
            HasEmpathySpecializationPrerequisite(),
            SenseMoodTargetPrerequisite(),
        ]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target_obj = _resolve_mood_sense_target(kwargs)
        if target_obj is None:
            return ActionResult(success=False, message=_NO_TARGET_MESSAGE)

        target_sheet = resolve_actor_sheet(target_obj)
        if target_sheet is None:
            return ActionResult(success=False, message=_NO_SHEET_MESSAGE)

        actor_sheet = resolve_actor_sheet(actor)
        resolved = _resolve_sense_mood_check(actor_sheet)
        if isinstance(resolved, ActionResult):
            return resolved
        specialization, check_type = resolved

        from world.checks.services import perform_check  # noqa: PLC0415

        result = perform_check(
            actor,
            check_type,
            target_difficulty=MOOD_SENSE_TARGET_DIFFICULTY,
            specialization=specialization,
        )
        if result.success_level <= 0:
            return ActionResult(success=False, message=_MISS_MESSAGE)

        target_name = target_obj.key
        mood = target_sheet.current_mood
        if mood is None:
            return ActionResult(success=True, message=_SETTLED_MESSAGE.format(name=target_name))
        return ActionResult(
            success=True,
            message=_SENSED_MESSAGE.format(name=target_name, mood=mood.name.lower()),
        )
