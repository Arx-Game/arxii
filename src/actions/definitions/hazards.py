"""Hazard-response actions (#2846): the player's answer to a hazard prompt.

``hazard_endure`` (tough it out) and ``hazard_retreat`` (flee to safety) are
the two one-click dispatches on the hazard prompt card; cover-up and
seek-shade route through the existing outfit / room-position surfaces. Both
target SELF and resolve against the character's currently-prompted hazard
condition instance (any environmental hazard with a HazardResponseState).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType

if TYPE_CHECKING:
    from datetime import datetime

    from evennia.objects.models import ObjectDB

    from world.conditions.models import ConditionInstance


def _prompted_hazard_instance(actor: ObjectDB) -> ConditionInstance | None:
    """The actor's unresolved hazard-prompted condition instance, or None."""
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    return (
        ConditionInstance.objects.filter(
            target=actor,
            resolved_at__isnull=True,
            hazard_response__isnull=False,
        )
        .select_related("condition", "current_stage")
        .first()
    )


def _endure_deadline() -> datetime:
    """Real-time deadline equivalent to ENDURE_IC_HOURS of IC time."""
    from django.utils import timezone  # noqa: PLC0415

    from world.game_clock.services import (  # noqa: PLC0415
        get_ic_now,
        get_real_time_for_ic_date,
    )
    from world.species.sun_constants import ENDURE_IC_HOURS  # noqa: PLC0415

    ic_now = get_ic_now()
    if ic_now is not None:
        real = get_real_time_for_ic_date(ic_now + timedelta(hours=ENDURE_IC_HOURS))
        if real is not None:
            return real
    return timezone.now() + timedelta(hours=ENDURE_IC_HOURS)


@dataclass
class HazardEndureAction(Action):
    """Tough it out: stay put and take what the hazard deals.

    PLACEHOLDER (#2846): v1 always succeeds — the design calls for a
    willpower-flavored check that is deliberately easy for characters whose
    own species carries the bane/allergy; the check wiring is a content-pass
    follow-through on the spec issue, not new machinery.
    """

    key: str = "hazard_endure"
    name: str = "Tough It Out"
    icon: str = "flame"
    category: str = "hazard"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.conditions.hazard_prompt import mark_endured  # noqa: PLC0415

        instance = _prompted_hazard_instance(actor)
        if instance is None:
            return ActionResult(success=False, message="No hazard is pressing you right now.")
        mark_endured(instance, until=_endure_deadline())
        return ActionResult(
            success=True,
            message=("You grit your teeth and endure; you will not be moved, whatever it costs."),
            broadcast=f"{actor.key} stands firm against the elements.",
        )


@dataclass
class HazardRetreatAction(Action):
    """Retreat to safety: the auto-flee pathing, chosen consciously."""

    key: str = "hazard_retreat"
    name: str = "Retreat To Safety"
    icon: str = "door-open"
    category: str = "hazard"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.conditions.hazard_prompt import mark_responded  # noqa: PLC0415
        from world.species.sun_refuge import flee_to_sun_refuge  # noqa: PLC0415

        instance = _prompted_hazard_instance(actor)
        if instance is None:
            return ActionResult(success=False, message="No hazard is pressing you right now.")
        if not flee_to_sun_refuge(actor):
            return ActionResult(
                success=False,
                message="There is no reachable shelter nearby; you must make do here.",
            )
        mark_responded(instance)
        return ActionResult(success=True, message="You retreat to cover.")
