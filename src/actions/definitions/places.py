"""Join/leave current typed places and existing unscoped resolved-Place calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from actions.base import Action
from actions.definitions.room_target_helpers import (
    MENU_TARGET_KEY,
    UNAVAILABLE,
    RoomTargetPrerequisite,
    apply_room_enhancements,
    at_place,
    current_persona,
    emit_room_intent,
    room_target,
)
from actions.prerequisites import HasCharacterSheetPrerequisite, Prerequisite
from actions.target_menu_types import MenuTargetKind
from actions.types import ActionContext, ActionResult, TargetType
from world.scenes.place_models import Place
from world.scenes.place_services import join_place, leave_place
from world.scenes.services import active_persona_for_sheet

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models import ActionEnhancement


_LEAVE_PLACE_KEY = "leave_place"


class _PlaceAction(Action):
    menu_kinds: ClassVar[frozenset[MenuTargetKind]] = frozenset({MenuTargetKind.PLACES})

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite(), RoomTargetPrerequisite(self)]

    def _apply_enhancements(
        self,
        context: ActionContext,
        actor: ObjectDB | None,
        enhancements: list[ActionEnhancement] | None,
    ) -> None:
        apply_room_enhancements(
            context, actor, enhancements, super()._apply_enhancements, self.menu_kinds
        )

    def _emit_intent(self, context: ActionContext, actor: ObjectDB | None) -> ActionResult | None:
        return emit_room_intent(context, actor, super()._emit_intent, self.menu_kinds)

    def is_applicable(self, actor: ObjectDB | None, *, kwargs: dict[str, Any]) -> bool:
        resolved = room_target(actor, kwargs, self.menu_kinds)
        if resolved is None or resolved.place is None or current_persona(actor) is None:
            return False
        present = at_place(actor, resolved.place)
        return present if self.key == _LEAVE_PLACE_KEY else not present

    def _place(self, actor: ObjectDB, kwargs: dict[str, Any]) -> Place | None:
        if MENU_TARGET_KEY in kwargs:
            if not self.is_applicable(actor, kwargs=kwargs):
                return None
            resolved = room_target(actor, kwargs, self.menu_kinds)
            return resolved.place if resolved is not None else None
        return kwargs.get("place")


@dataclass
class JoinPlaceAction(_PlaceAction):
    """Join as the actor's active persona using the existing presence service."""

    key: str = "join_place"
    name: str = "Join Place"
    icon: str = "account-group"
    category: str = "scenes"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        place = self._place(actor, kwargs)
        if place is None:
            return ActionResult(
                success=False,
                message=UNAVAILABLE if MENU_TARGET_KEY in kwargs else "Join which place?",
            )
        persona = active_persona_for_sheet(actor.sheet_data)
        presence = join_place(place=place, persona=persona)
        data = {"presence_id": presence.pk} if MENU_TARGET_KEY in kwargs else {"presence": presence}
        return ActionResult(success=True, message=f"You join {place.name}.", data=data)


@dataclass
class LeavePlaceAction(_PlaceAction):
    """Leave the place occupied by the actor's current active persona."""

    key: str = "leave_place"
    name: str = "Leave Place"
    icon: str = "account-group-off"
    category: str = "scenes"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        place = self._place(actor, kwargs)
        if place is None:
            return ActionResult(
                success=False,
                message=UNAVAILABLE if MENU_TARGET_KEY in kwargs else "Leave which place?",
            )
        persona = active_persona_for_sheet(actor.sheet_data)
        if not leave_place(place=place, persona=persona):
            return ActionResult(success=False, message="You aren't at that place.")
        return ActionResult(success=True, message=f"You leave {place.name}.")
