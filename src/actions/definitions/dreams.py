"""Dream realm actions — sleep, dreamwalk, descend, ascend (#2290)."""

from dataclasses import dataclass
from typing import Any

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType

_NO_SHEET_MSG = "You have no character sheet."


@dataclass
class SleepAction(Action):
    """Voluntarily sleep to enter the dream realm.

    Applies the Sleeping condition (capability-zeroing, same as Unconscious
    but voluntary). The character's perception relocates to the dream space
    via ``perceives_dreamside()``.
    """

    key: str = "sleep"
    name: str = "Sleep"
    icon: str = "moon"
    category: str = "vitals"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: Any,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.conditions.models import ConditionTemplate  # noqa: PLC0415
        from world.conditions.services import apply_condition  # noqa: PLC0415
        from world.vitals.constants import SLEEPING_CONDITION_NAME  # noqa: PLC0415

        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return ActionResult(success=False, message=_NO_SHEET_MSG)
        if sheet is None:
            return ActionResult(success=False, message=_NO_SHEET_MSG)

        template = ConditionTemplate.objects.filter(name=SLEEPING_CONDITION_NAME).first()
        if template is None:
            return ActionResult(
                success=False,
                message="The dream realm is not yet available.",
            )

        apply_condition(target=actor, condition=template)
        return ActionResult(success=True, message="You drift into sleep...")


@dataclass
class DescendAction(Action):
    """Descend from a dream reflection into the deep dreaming (#2290).

    Moves the character's ObjectDB to the dream reflection's descent_target
    room. Requires the character to be dreamside (Sleeping/Unconscious).
    """

    key: str = "descend"
    name: str = "Descend"
    icon: str = "arrow-down"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: Any,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.dreams.models import DreamReflection  # noqa: PLC0415
        from world.vitals.services import perceives_dreamside  # noqa: PLC0415

        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return ActionResult(success=False, message=_NO_SHEET_MSG)
        if sheet is None:
            return ActionResult(success=False, message=_NO_SHEET_MSG)
        if not perceives_dreamside(sheet):
            return ActionResult(success=False, message="You must be dreaming to descend.")

        # Find the dream reflection for the character's current room
        reflection = DreamReflection.objects.for_waking_room(actor.location)
        if reflection is None or reflection.descent_target is None:
            return ActionResult(
                success=False,
                message="There is no deeper dream to descend into from here.",
            )

        actor.location = reflection.descent_target.objectdb
        actor.save(update_fields=["db_location"])
        return ActionResult(
            success=True,
            message="You sink deeper into the dream...",
        )


@dataclass
class AscendAction(Action):
    """Ascend from the deep dreaming back to a dream reflection (#2290).

    Returns the character to the dream room of the nearest active reflection
    whose descent_target matches their current location.
    """

    key: str = "ascend"
    name: str = "Ascend"
    icon: str = "arrow-up"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: Any,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.dreams.models import DreamReflection  # noqa: PLC0415

        # Find the reflection whose descent_target is the character's current room
        reflection = DreamReflection.objects.filter(
            descent_target_id=actor.location.pk,
            is_active=True,
        ).first()
        if reflection is None:
            return ActionResult(
                success=False,
                message="You cannot find your way back from here.",
            )

        actor.location = reflection.dream_room.objectdb
        actor.save(update_fields=["db_location"])
        return ActionResult(
            success=True,
            message="You rise back toward the surface of the dream...",
        )


@dataclass
class DreamwalkAction(Action):
    """Travel to a bonded dreamer's dreamspace (#2290).

    Gated by existing relationship infrastructure: the dreamer must have a
    RELATIONSHIP_TRACK or RELATIONSHIP_CAPSTONE thread to the target, or an
    active soul tether bond. Characters sleeping in the same physical room
    share a dreamspace automatically (no dreamwalk needed).

    On success, the dreamer's perception relocates to the target's dream
    room. A ``DreamwalkPresence`` row anchors the walker to the host
    *sheet* (#3003) rather than stashing a destination; the escape lever
    (``wake there`` — wake at the target's location instead of own body's)
    resolves the destination dynamically from the host's current location
    at wake time, so it still follows the host if they've moved.
    """

    key: str = "dreamwalk"
    name: str = "Dreamwalk"
    icon: str = "wind"
    category: str = "magic"
    target_type: TargetType = TargetType.SINGLE

    def execute(  # noqa: C901, PLR0911
        self,
        actor: Any,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.dreams.services import (  # noqa: PLC0415
            get_dream_space,
            has_dream_bond,
            start_dreamwalk,
        )
        from world.vitals.services import perceives_dreamside  # noqa: PLC0415

        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return ActionResult(success=False, message=_NO_SHEET_MSG)
        if sheet is None:
            return ActionResult(success=False, message=_NO_SHEET_MSG)

        # Must be dreamside to dreamwalk
        if not perceives_dreamside(sheet):
            return ActionResult(
                success=False,
                message="You must be dreaming to dreamwalk.",
            )

        # Resolve the target character
        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="Dreamwalk to whom?")

        try:
            target_sheet = target.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            target_sheet = None
        if target_sheet is None:
            return ActionResult(success=False, message="You cannot find that person in the dream.")

        # Target must also be dreamside
        if not perceives_dreamside(target_sheet):
            return ActionResult(
                success=False,
                message=f"{target.key} is not dreaming.",
            )

        # Check for same room (no dreamwalk needed)
        if actor.location == target.location:
            return ActionResult(
                success=False,
                message=f"You are already sharing a dreamspace with {target.key}.",
            )

        # Gate: check for RELATIONSHIP_TRACK/CAPSTONE thread or soul tether
        if not has_dream_bond(sheet, target_sheet):
            return ActionResult(
                success=False,
                message="You have no bond strong enough to reach that person in dreams.",
            )

        # Relocate perception to the target's dream room
        target_dream_room = get_dream_space(room=target.location)
        if target_dream_room is None:
            return ActionResult(
                success=False,
                message="You cannot find their dream.",
            )

        # Anchor the walker's perception to the target's dreamspace (#3003) —
        # the presence row is the escape lever ``wake`` reads via end_dreamwalk().
        start_dreamwalk(dreamer=sheet, host=target_sheet)

        return ActionResult(
            success=True,
            message=f"You dreamwalk toward {target.key}...",
        )
