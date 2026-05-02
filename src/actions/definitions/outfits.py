"""Outfit-related actions: apply_outfit, undress."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType
from flows.constants import EventName
from flows.object_states.outfit_state import OutfitState
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location
from flows.service_functions.outfits import (
    apply_outfit as apply_outfit_service,
    undress as undress_service,
)
from world.items.exceptions import InventoryError
from world.items.models import Outfit

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


@dataclass
class ApplyOutfitAction(Action):
    """Wear a saved outfit. Equips all of the outfit's slots atomically."""

    key: str = "apply_outfit"
    name: str = "Wear Outfit"
    icon: str = "wardrobe"
    category: str = "items"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = EventName.BEFORE_APPLY_OUTFIT.value
    result_event: str | None = EventName.APPLY_OUTFIT.value

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        outfit_id = kwargs.get("outfit_id")
        if outfit_id is None:
            return ActionResult(success=False, message="Wear which outfit?")
        try:
            outfit = Outfit.objects.get(pk=outfit_id)
        except Outfit.DoesNotExist:
            return ActionResult(
                success=False,
                message="That outfit no longer exists.",
            )

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        outfit_state = OutfitState(outfit, context=sdm)

        try:
            apply_outfit_service(actor_state, outfit_state)
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)

        message_location(
            actor_state,
            "$You() $conj(change) into {outfit}.",
            mapping={"outfit": outfit.name},
        )
        return ActionResult(success=True)


@dataclass
class UndressAction(Action):
    """Remove all currently-worn items. Items go back to inventory."""

    key: str = "undress"
    name: str = "Undress"
    icon: str = "shirt-off"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    intent_event: str | None = EventName.BEFORE_UNDRESS.value
    result_event: str | None = EventName.UNDRESS.value

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)

        try:
            undress_service(actor_state)
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)

        message_location(actor_state, "$You() $conj(undress).")
        return ActionResult(success=True)
