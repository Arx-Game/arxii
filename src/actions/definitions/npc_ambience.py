"""Servant pampering + expulsion actions (#2989).

``ServantPrepareMealAction``/``ServantPrepareBathAction`` wrap
``world.npc_services.servant_ambience`` (delay+echo pampering, mirroring
``GetAction``'s servant-fetch interception idiom). ``ExpelCharacterAction``/
``LiftExpulsionBarAction`` wrap ``world.npc_services.expulsion_services`` —
the unresistable OOC soft gate for showing a disruptive character out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import IsRoomOwnerPrerequisite, Prerequisite
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from actions.types import ActionContext


def _actor_persona_or_none(actor: ObjectDB):
    """Resolve the actor's active persona, or None if unavailable."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    try:
        sheet = actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None
    return active_persona_for_sheet(sheet)


@dataclass
class ServantPrepareMealAction(Action):
    """Have the household servant prepare a meal — pure pampering ambience (#2989).

    Gated like servant fetch (owner/tenant standing + an active SERVANT in
    reach), not owner-only — any resident with standing may be pampered.
    """

    key: str = "servant_prepare_meal"
    name: str = "Servant: Prepare Meal"
    icon: str = "utensils"
    category: str = "npc_services"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.npc_services.servant_ambience import (  # noqa: PLC0415
            can_servant_pamper,
            prepare_meal,
        )

        if not can_servant_pamper(actor=actor):
            return ActionResult(success=False, message="There's no servant here to ask.")

        prepare_meal(actor)
        return ActionResult(success=True, message="A servant bows and departs to prepare a meal.")


@dataclass
class ServantPrepareBathAction(Action):
    """Have the household servant draw a bath — ambience + a flat fatigue recovery (#2989).

    Gated like servant fetch (owner/tenant standing + an active SERVANT in
    reach), not owner-only — any resident with standing may be pampered.
    """

    key: str = "servant_prepare_bath"
    name: str = "Servant: Draw Bath"
    icon: str = "bath"
    category: str = "npc_services"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.npc_services.servant_ambience import (  # noqa: PLC0415
            can_servant_pamper,
            prepare_bath,
        )

        if not can_servant_pamper(actor=actor):
            return ActionResult(success=False, message="There's no servant here to ask.")

        prepare_bath(actor)
        return ActionResult(success=True, message="A servant bows and departs to draw a bath.")


@dataclass
class ExpelCharacterAction(Action):
    """Show a disruptive character out and bar their re-entry (#2989).

    OOC soft gate — CANNOT be resisted: no check, no roll, no prerequisite
    bypass on the target, regardless of the target's character power.

    Kwargs:
        target: The ObjectDB character to expel (must be co-located).
    """

    key: str = "expel_character"
    name: str = "Expel"
    icon: str = "door-open"
    category: str = "npc_services"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsRoomOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="Expel whom?")
        if target == actor:
            return ActionResult(success=False, message="You can't expel yourself.")
        if actor.location is None or target.location != actor.location:
            return ActionResult(success=False, message="They aren't here.")

        persona = _actor_persona_or_none(actor)
        if persona is None:
            return ActionResult(success=False, message="You have no active persona.")

        from world.npc_services.expulsion_services import expel_character  # noqa: PLC0415

        success, message = expel_character(actor=actor, target=target, imposed_by=persona)
        return ActionResult(success=success, message=message)


@dataclass
class LiftExpulsionBarAction(Action):
    """Lift an active expulsion bar in the actor's room (#2989).

    Kwargs:
        name: The barred character's name (case-insensitive).
    """

    key: str = "lift_expulsion_bar"
    name: str = "Lift Expulsion Bar"
    icon: str = "door-open"
    category: str = "npc_services"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsRoomOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        name = (kwargs.get("name") or "").strip()
        if not name:
            return ActionResult(success=False, message="Lift the bar on whom?")
        if actor.location is None:
            return ActionResult(success=False, message="You're not in a room.")

        from world.npc_services.expulsion_services import lift_expulsion_bar  # noqa: PLC0415

        success, message = lift_expulsion_bar(room=actor.location, name=name)
        return ActionResult(success=success, message=message)
