"""Prerequisite interface and initial implementations for actions.

Prerequisites are thin wrappers around existing system queries. They answer
"can this actor do this action right now, possibly to this target?"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

CANNOT_BE_USED_MESSAGE = "That can't be used."
CANNOT_SEE_MESSAGE = "You can't see that."

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def resolve_actor_sheet(actor: ObjectDB) -> Any:
    """Return the actor's ``CharacterSheet``, or ``None`` if they have none."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        return actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None


@dataclass
class Prerequisite:
    """Base class for action prerequisites.

    Subclasses implement ``is_met`` to check a specific condition.
    Returns (True, "") if met, or (False, "human-readable reason") if not.
    """

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        raise NotImplementedError


@dataclass
class HasCharacterSheetPrerequisite(Prerequisite):
    """Actor must have a CharacterSheet."""

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        try:
            actor.sheet_data  # noqa: B018
        except (AttributeError, ObjectDoesNotExist):
            return False, "No active character."
        return True, ""


@dataclass
class HoldsCapabilityPrerequisite(Prerequisite):
    """Actor must hold the named capability (effective value >= 1)."""

    capability_name: str

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.conditions.models import CapabilityType  # noqa: PLC0415
        from world.conditions.services import get_effective_capability_value  # noqa: PLC0415

        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return False, "No active character."
        capability = CapabilityType.objects.filter(name=self.capability_name).first()
        if capability is None:
            return False, "You cannot shift forms at will."
        if get_effective_capability_value(sheet, capability) >= 1:
            return True, ""
        return False, "You cannot shift forms at will."


@dataclass
class StaffOnlyPrerequisite(Prerequisite):
    """The actor's account must be staff (GM tooling gate)."""

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from core_management.permissions import is_staff_observer  # noqa: PLC0415

        if is_staff_observer(actor):
            return True, ""
        return False, "Staff only."


@dataclass
class IsRoomTenantPrerequisite(Prerequisite):
    """The actor's active persona must actively tenant the room they're standing in (#670)."""

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.locations.services import is_tenant  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        room = actor.location
        if room is None:
            return False, "You're not in a room."
        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return False, "Only characters can do that."
        persona = active_persona_for_sheet(sheet)
        if is_tenant(persona, room):
            return True, ""
        return False, "You don't live here."


@dataclass
class IsRoomOwnerPrerequisite(Prerequisite):
    """The actor's active persona must own the room they're standing in (#1470)."""

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.locations.services import is_owner  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        room = actor.location
        if room is None:
            return False, "You're not in a room."
        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return False, "Only characters can edit rooms."
        persona = active_persona_for_sheet(sheet)
        if is_owner(persona, room):
            return True, ""
        return False, "You don't own this room."


@dataclass
class HoldsItemPrerequisite(Prerequisite):
    """The actor must be holding the item passed as ``kwargs['item']``."""

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from actions.definitions.item_helpers import resolve_item_instance  # noqa: PLC0415
        from flows.object_states.item_state import ItemState  # noqa: PLC0415

        item_obj = (context or {}).get("kwargs", {}).get("item")
        if item_obj is None:
            return False, "Use what?"
        instance = resolve_item_instance(item_obj)
        if instance is None:
            return False, "That isn't an item."
        if not ItemState(instance, context=None).is_in_possession(actor):
            return False, "You aren't holding that."
        return True, ""


def _is_visible_to(actor, target) -> bool:
    """Whether ``actor`` can perceive ``target``.

    MVP proxy: same-location presence (you perceive what is in your room).
    TODO(#1225): replace with a real perception/visibility
    system (darkness, stealth, line-of-sight).
    """
    return target.location in (actor.location, actor)


@dataclass
class ItemUsablePrerequisite(Prerequisite):
    """The item's template must have an on-use pool (usable); consumables must
    have charges remaining. Mirrors use_item's preconditions / #1026 is_usable."""

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from actions.definitions.item_helpers import resolve_item_instance  # noqa: PLC0415

        item_obj = (context or {}).get("kwargs", {}).get("item")
        instance = resolve_item_instance(item_obj) if item_obj is not None else None
        if instance is None:
            return False, CANNOT_BE_USED_MESSAGE
        template = instance.template
        if not template.is_usable:
            return False, CANNOT_BE_USED_MESSAGE
        if template.is_consumable and instance.charges <= 0:
            return False, "There are no uses left."
        return True, ""


def _check_item_target(actor: ObjectDB, target: ObjectDB) -> tuple[bool, str]:
    """Validate an ITEM-kind on-use target: must be a resolvable, reachable, visible item."""
    from actions.definitions.item_helpers import resolve_item_instance  # noqa: PLC0415
    from flows.object_states.item_state import ItemState  # noqa: PLC0415

    target_instance = resolve_item_instance(target)
    if target_instance is None:
        return False, "You can't use that on that."
    if not ItemState(target_instance, context=None).is_reachable_by(actor):
        return False, "That isn't within reach."
    if not _is_visible_to(actor, target):
        return False, CANNOT_SEE_MESSAGE
    return True, ""


def _check_character_target(actor: ObjectDB, target: ObjectDB) -> tuple[bool, str]:
    """Validate a CHARACTER-kind on-use target: must be a character present and visible."""
    if not target.is_typeclass("typeclasses.characters.Character", exact=False):
        return False, "That can only be used on a character."
    if target.location != actor.location:
        return False, "They aren't here."
    if not _is_visible_to(actor, target):
        return False, CANNOT_SEE_MESSAGE
    return True, ""


def _check_room_target(actor: ObjectDB, target: ObjectDB) -> tuple[bool, str]:
    """Validate a ROOM-kind on-use target: must be a room the actor occupies and can see."""
    if not target.is_typeclass("typeclasses.rooms.Room", exact=False):
        return False, "That can only be used on a place."
    if actor.location not in (target.location, target):
        return False, "They aren't here."
    if not _is_visible_to(actor, target):
        return False, CANNOT_SEE_MESSAGE
    return True, ""


@dataclass
class OnUseTargetPrerequisite(Prerequisite):
    """Enforce the item's on_use_target_kind contract on the effect-target.

    Null kind => self-use only (a supplied target fails). A set kind => an
    external target of that kind is required, reachable, and visible.
    """

    def is_met(  # noqa: PLR0911
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from actions.constants import TargetKind  # noqa: PLC0415
        from actions.definitions.item_helpers import resolve_item_instance  # noqa: PLC0415

        item_obj = (context or {}).get("kwargs", {}).get("item")
        instance = resolve_item_instance(item_obj) if item_obj is not None else None
        if instance is None:
            return False, CANNOT_BE_USED_MESSAGE
        kind = instance.template.on_use_target_kind

        if kind is None:
            if target is not None:
                return False, "That can't be used on others."
            return True, ""

        if target is None:
            return False, "Use it on what?"

        if kind == TargetKind.ITEM:
            return _check_item_target(actor, target)
        if kind == TargetKind.CHARACTER:
            return _check_character_target(actor, target)
        if kind == TargetKind.ROOM:
            return _check_room_target(actor, target)

        # TargetKind.PERSONA and any future unhandled kinds — fail closed.
        return False, "That can't be used on that."


@dataclass
class PendingRitualEffectPrerequisite(Prerequisite):
    """Actor must have a PendingRitualEffect for the named ritual.

    Used by WeaveThreadAction (requires 'Rite of Weaving') and ImbueAction
    (requires 'Rite of Imbuing'). The finisher action consumes the pending
    effect on success.
    """

    ritual_name: str

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from world.magic.models import PendingRitualEffect, Ritual  # noqa: PLC0415

        ritual = Ritual.objects.filter(name__iexact=self.ritual_name).first()
        if not ritual:
            return False, f"You must perform {self.ritual_name} first."
        exists = PendingRitualEffect.objects.filter(
            character=actor.sheet_data, ritual=ritual
        ).exists()
        if not exists:
            return False, f"You must perform {self.ritual_name} first."
        return True, ""
