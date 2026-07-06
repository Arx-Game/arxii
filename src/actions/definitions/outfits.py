"""Outfit-related actions: apply_outfit, undress."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.prerequisites import OwnsOutfitPrerequisite, Prerequisite
from actions.types import ActionContext, ActionResult, TargetType
from flows.constants import EventName
from flows.object_states.outfit_state import OutfitState
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location
from flows.service_functions.outfits import (
    add_outfit_slot as add_outfit_slot_service,
    apply_outfit as apply_outfit_service,
    delete_outfit as delete_outfit_service,
    remove_outfit_slot as remove_outfit_slot_service,
    rename_outfit as rename_outfit_service,
    save_outfit as save_outfit_service,
    undress as undress_service,
)
from world.items.exceptions import InventoryError, ItemError
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


@dataclass
class SaveOutfitAction(Action):
    """Snapshot the actor's currently-equipped items into a new Outfit."""

    key: str = "save_outfit"
    name: str = "Save Outfit"
    icon: str = "content-save"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        wardrobe = kwargs.get("wardrobe")
        name = kwargs.get("name")
        description = kwargs.get("description", "")
        if wardrobe is None or not name:
            return ActionResult(success=False, message="Save with which wardrobe, and what name?")
        try:
            sheet = actor.sheet_data
        except AttributeError:
            return ActionResult(success=False, message="No active character.")
        try:
            outfit = save_outfit_service(
                character_sheet=sheet, wardrobe=wardrobe, name=name, description=description
            )
        except ItemError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, data={"outfit": outfit})


@dataclass
class RenameOutfitAction(Action):
    """Rename/redescribe a saved outfit."""

    key: str = "rename_outfit"
    name: str = "Rename Outfit"
    icon: str = "pencil"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [OwnsOutfitPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        outfit = kwargs.get("outfit")
        name = kwargs.get("name")
        if outfit is None or not name:
            return ActionResult(success=False, message="Rename which outfit, to what?")
        rename_outfit_service(outfit=outfit, name=name, description=kwargs.get("description", ""))
        return ActionResult(success=True)


@dataclass
class DeleteOutfitAction(Action):
    """Delete a saved outfit definition (items are unaffected)."""

    key: str = "delete_outfit"
    name: str = "Delete Outfit"
    icon: str = "delete"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [OwnsOutfitPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        outfit = kwargs.get("outfit")
        if outfit is None:
            return ActionResult(success=False, message="Delete which outfit?")
        delete_outfit_service(outfit)
        return ActionResult(success=True)


@dataclass
class AddOutfitSlotAction(Action):
    """Add or replace a slot in a saved outfit."""

    key: str = "add_outfit_slot"
    name: str = "Add Outfit Slot"
    icon: str = "plus"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [OwnsOutfitPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        outfit = kwargs.get("outfit")
        item_instance = kwargs.get("item_instance")
        body_region = kwargs.get("body_region")
        equipment_layer = kwargs.get("equipment_layer")
        if outfit is None or item_instance is None or not body_region or not equipment_layer:
            return ActionResult(success=False, message="Add what item, to which slot?")
        try:
            slot = add_outfit_slot_service(
                outfit=outfit,
                item_instance=item_instance,
                body_region=body_region,
                equipment_layer=equipment_layer,
            )
        except ItemError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, data={"slot": slot})


@dataclass
class RemoveOutfitSlotAction(Action):
    """Remove a slot from a saved outfit (idempotent)."""

    key: str = "remove_outfit_slot"
    name: str = "Remove Outfit Slot"
    icon: str = "minus"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [OwnsOutfitPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        outfit = kwargs.get("outfit")
        body_region = kwargs.get("body_region")
        equipment_layer = kwargs.get("equipment_layer")
        if outfit is None or not body_region or not equipment_layer:
            return ActionResult(success=False, message="Remove which slot?")
        remove_outfit_slot_service(
            outfit=outfit, body_region=body_region, equipment_layer=equipment_layer
        )
        return ActionResult(success=True)
