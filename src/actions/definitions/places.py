"""Places join/leave Actions (#1866).

Thin wrappers over ``world.scenes.place_services.join_place``/``leave_place``
— the same services ``PlaceViewSet.join``/``.leave`` call. No location gate
is added here, matching the existing web behavior exactly (verified during
spec — no co-location check exists in PlaceViewSet today); adding one would
be a behavior change out of scope for a coverage-gap fix.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.prerequisites import HasCharacterSheetPrerequisite, Prerequisite
from actions.types import ActionResult, TargetType
from world.scenes.place_services import join_place, leave_place
from world.scenes.services import active_persona_for_sheet

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


@dataclass
class JoinPlaceAction(Action):
    """Join a Place in the actor's current room (as their active persona)."""

    key: str = "join_place"
    name: str = "Join Place"
    icon: str = "account-group"
    category: str = "scenes"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        place = kwargs.get("place")
        if place is None:
            return ActionResult(success=False, message="Join which place?")
        persona = active_persona_for_sheet(actor.sheet_data)
        presence = join_place(place=place, persona=persona)
        return ActionResult(
            success=True, message=f"You join {place.name}.", data={"presence": presence}
        )


@dataclass
class LeavePlaceAction(Action):
    """Leave the Place the actor's active persona currently occupies."""

    key: str = "leave_place"
    name: str = "Leave Place"
    icon: str = "account-group-off"
    category: str = "scenes"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        place = kwargs.get("place")
        if place is None:
            return ActionResult(success=False, message="Leave which place?")
        persona = active_persona_for_sheet(actor.sheet_data)
        left = leave_place(place=place, persona=persona)
        if not left:
            return ActionResult(success=False, message="You aren't at that place.")
        return ActionResult(success=True, message=f"You leave {place.name}.")
