"""Prerequisite interface and initial implementations for actions.

Prerequisites are thin wrappers around existing system queries. They answer
"can this actor do this action right now, possibly to this target?"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

CANNOT_BE_USED_MESSAGE = "That can't be used."
CANNOT_SEE_MESSAGE = "You can't see that."
NO_ACTIVE_CHARACTER_MESSAGE = "No active character."
ONLY_CHARACTERS_MESSAGE = "Only characters can do that."
NOT_HOLDING_MESSAGE = "You aren't holding that."

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
            return False, NO_ACTIVE_CHARACTER_MESSAGE
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
            return False, NO_ACTIVE_CHARACTER_MESSAGE
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
class MinimumGMLevelPrerequisite(Prerequisite):
    """Actor must hold at least ``minimum_level`` GM trust, with a staff bypass (#2117).

    Generalizes the staff-bypass + ``gm_level_index`` compare proven in
    ``world.combat.scaling.validate_stakes_requirement`` into a reusable
    Prerequisite for table-running GM tools (setstage/setsituation/pemit/grant_item).

    A missing ``GMProfile`` always fails -- even against a ``STARTING``
    requirement -- since ``STARTING`` still means "approved GM," not "any
    account." This deliberately differs from ``validate_stakes_requirement``,
    which treats a missing profile as ``STARTING`` (that function only ever
    runs against an account already GMing a live encounter; this Prerequisite
    also has to exclude accounts with no GM standing at all).
    """

    minimum_level: str

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from core_management.permissions import is_staff_observer  # noqa: PLC0415
        from world.gm.constants import GMLevel, gm_level_index  # noqa: PLC0415
        from world.gm.models import GMProfile  # noqa: PLC0415

        if is_staff_observer(actor):
            return True, ""

        try:
            account = actor.active_account
        except AttributeError:
            account = None
        if account is None:
            return False, "GM trust required."

        try:
            level = account.gm_profile.level
        except GMProfile.DoesNotExist:
            return False, "GM trust required."

        if gm_level_index(level) < gm_level_index(self.minimum_level):
            required_display = GMLevel(self.minimum_level).label
            return False, f"Requires {required_display} or higher."
        return True, ""


@dataclass
class IsSceneGMPrerequisite(Prerequisite):
    """Actor must be staff, or the GM of the active scene at their location (#2118).

    Staff bypass, else resolves the actor's active scene
    (``get_active_scene``, ``world/scenes/interaction_services.py:38``) and requires
    ``scene.is_gm(actor.active_account)``. Strict sibling of
    ``actor_can_administer_scene`` -- deliberately excludes scene co-owners, so
    administering a scene does not by itself grant catalog-check/award/condition
    adjudication power. Mirrors ``_actor_may_gm_encounter``
    (``actions/definitions/gm_combat.py:72-79``), including its refusal message.
    """

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from commands.utils.gm_resolution import resolve_account_or_none  # noqa: PLC0415
        from core_management.permissions import is_staff_observer  # noqa: PLC0415
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

        if is_staff_observer(actor):
            return True, ""

        account = resolve_account_or_none(actor)
        scene = get_active_scene(actor.location)
        if scene is not None and scene.is_gm(account):
            return True, ""
        return False, "Only the scene's GM or staff can do that."


def _resolve_room_from_kwarg_or_location(
    actor: ObjectDB, context: dict | None
) -> tuple[ObjectDB | None, str]:
    """Resolve the anchor room: the ``room_id`` kwarg (web canvas) when supplied,
    else the room the actor is standing in.

    Returns ``(room, "")`` on success, or ``(None, refusal_message)`` on failure.
    Shared by ``IsRoomOwnerPrerequisite`` and ``IsRoomTenantPrerequisite`` — both
    prerequisites need identical room-anchor resolution, differing only in what
    standing check they run against the resolved room.
    """
    kwargs = (context or {}).get("kwargs", {})
    room_id = kwargs.get("room_id")
    if room_id:
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415

        profile = RoomProfile.objects.filter(objectdb_id=room_id).select_related("objectdb").first()
        if profile is None:
            return None, "No such room."
        return profile.objectdb, ""
    room = actor.location
    if room is None:
        return None, "You're not in a room."
    return room, ""


@dataclass
class IsRoomTenantPrerequisite(Prerequisite):
    """The actor's active persona must have owner OR tenant standing in the room
    they're standing in (#670, widened #2036).

    ``is_tenant`` alone does not imply ``is_owner`` — a room's deeded owner has
    no guarantee of an active ``LocationTenancy`` row (e.g. immediately after
    ``transfer_ownership``, which mints no tenancy). Checking both composes the
    full "I have any standing here" gate without a second near-duplicate
    prerequisite class — the name predates this widening (#670) but the shape
    (any of owner/tenant, both of which already compose org-derived standing
    via ``is_owner``/``is_tenant``) is exactly "does this persona have standing
    at this room," which every current caller (``SetPrimaryHomeAction``,
    ``TagRoomResonanceAction``, ``UntagRoomResonanceAction``) wants.

    Anchors on the ``room_id`` kwarg when supplied (web canvas), else the
    actor's own location — the same resolution ``IsRoomOwnerPrerequisite`` uses,
    needed so ``RoomEditAction`` (#2452) can use this prerequisite for its own
    room_id-aware targeting.
    """

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.locations.services import is_owner, is_tenant  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        room, error = _resolve_room_from_kwarg_or_location(actor, context)
        if room is None:
            return False, error
        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return False, ONLY_CHARACTERS_MESSAGE
        persona = active_persona_for_sheet(sheet)
        if is_owner(persona, room) or is_tenant(persona, room):
            return True, ""
        return False, "You have no standing in this room."


@dataclass
class IsRoomOwnerPrerequisite(Prerequisite):
    """The actor's active persona must own the anchor room (#1470, #670 PR2).

    The anchor is the ``room_id`` kwarg when the web canvas supplies one
    (read via the kwargs-via-context convention), else the room the actor is
    standing in — the same resolution the actions themselves use.
    """

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.locations.services import is_owner  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        room, error = _resolve_room_from_kwarg_or_location(actor, context)
        if room is None:
            return False, error
        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return False, "Only characters can edit rooms."
        persona = active_persona_for_sheet(sheet)
        if is_owner(persona, room):
            return True, ""
        return False, "You don't own this room."


@dataclass
class IsExitRoomOwnerPrerequisite(Prerequisite):
    """The actor's active persona must own or tenant the exit's source room.

    Mirrors IsRoomOwnerPrerequisite, but resolves the room from the ``exit``
    kwarg's ``location`` (the room the exit sits in) rather than a
    ``room_id`` kwarg or the actor's own location — door-lock commands name
    an exit, not necessarily the room the actor currently stands in.
    """

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.locations.services import is_owner, is_tenant  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        exit_obj = (context or {}).get("kwargs", {}).get("exit")
        if exit_obj is None:
            return False, "Lock/unlock which exit?"
        room = exit_obj.location
        if room is None:
            return False, "That exit has no source room."
        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return False, ONLY_CHARACTERS_MESSAGE
        persona = active_persona_for_sheet(sheet)
        if is_owner(persona, room) or is_tenant(persona, room):
            return True, ""
        return False, "You don't have standing in that room."


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
            return False, NOT_HOLDING_MESSAGE
        return True, ""


@dataclass
class OwnsOutfitPrerequisite(Prerequisite):
    """The ``outfit`` kwarg must belong to the actor's own CharacterSheet."""

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        outfit = (context or {}).get("kwargs", {}).get("outfit")
        if outfit is None:
            return False, "Which outfit?"
        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return False, NO_ACTIVE_CHARACTER_MESSAGE
        if outfit.character_sheet_id == sheet.pk:
            return True, ""
        return False, "That isn't your outfit."


@dataclass
class OwnsItemInstancePrerequisite(Prerequisite):
    """The actor's own CharacterSheet must be the item's holder.

    Body/tenure-keyed ownership (mirrors ``_user_holds_item`` in
    ``world.items.views``) — the item need not exist as a physical ObjectDB
    in the world; crafting operates on ``ItemInstance`` directly. Reads
    ``item_instance`` from kwargs, or derives it from ``item_facet`` when
    only that's present (the detach path).
    """

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        kwargs = (context or {}).get("kwargs", {})
        item_instance = kwargs.get("item_instance")
        if item_instance is None:
            item_facet = kwargs.get("item_facet")
            if item_facet is not None:
                item_instance = item_facet.item_instance
        if item_instance is None:
            return False, "Use what?"
        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return False, NOT_HOLDING_MESSAGE
        if item_instance.holder_character_sheet_id != sheet.pk:
            return False, NOT_HOLDING_MESSAGE
        return True, ""


@dataclass
class CanStealPrerequisite(Prerequisite):
    """The ``target`` kwarg item must be steal-eligible for the actor (#1909).

    Visibility = eligibility: ``steal_permitted`` is the same target-side
    predicate the ``steal`` service re-checks at execution time; reading the
    ``target`` kwarg via the kwargs-via-context convention lets this gate see
    it before ``execute()`` runs.
    """

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from actions.definitions.item_helpers import resolve_item_instance  # noqa: PLC0415
        from flows.service_functions.inventory import steal_permitted  # noqa: PLC0415
        from world.items.exceptions import TheftNotPermitted  # noqa: PLC0415

        target_obj = (context or {}).get("kwargs", {}).get("target")
        if target_obj is None:
            return False, "Steal what?"
        instance = resolve_item_instance(target_obj)
        if instance is None:
            return False, "That can't be stolen."
        actor_sheet = resolve_actor_sheet(actor)
        if steal_permitted(actor_sheet, instance):
            return True, ""
        return False, TheftNotPermitted.user_message


class BlackmailAmmoPrerequisite(Prerequisite):
    """You can only blackmail someone with a secret you actually know about *them* (#1680).

    Visibility = eligibility (like the steal gate): the blackmail action is offered only
    against a target you hold ammo on. Reads the chosen ``secret_id`` + ``target`` from the
    kwargs-via-context convention, resolves both characters' sheets, and confirms the
    secret is about the target and known to the actor. On success ``BlackmailAction`` mints
    ``Leverage`` founded on this same secret.
    """

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from world.secrets.models import Secret  # noqa: PLC0415
        from world.secrets.services import character_knows_secret  # noqa: PLC0415

        kwargs = (context or {}).get("kwargs", {})
        target_obj = kwargs.get("target")
        secret_id = kwargs.get("secret_id")
        if target_obj is None:
            return False, "Blackmail whom?"
        if secret_id is None:
            return False, "Blackmail them with what? Name the secret you hold."
        actor_sheet = resolve_actor_sheet(actor)
        target_sheet = resolve_actor_sheet(target_obj)
        if actor_sheet is None or target_sheet is None:
            return False, "Blackmail needs two characters."
        secret = Secret.objects.filter(pk=secret_id).first()
        if secret is None or secret.subject_sheet_id != target_sheet.pk:
            return False, "That secret isn't about them."
        if not character_knows_secret(knower_sheet=actor_sheet, secret=secret):
            return False, "You don't know that secret."
        return True, ""


class LeverageHeldPrerequisite(Prerequisite):
    """Coerce is offered only against a target you hold leverage over (#1680).

    Visibility = eligibility: reads the ``target_persona_id`` kwarg, resolves its sheet,
    and confirms the actor holds standing leverage over it (minted by a prior Blackmail).
    The ``coerce_into_asset`` service re-checks this authoritatively at execution.
    """

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.secrets.services import has_leverage  # noqa: PLC0415

        kwargs = (context or {}).get("kwargs", {})
        target_persona_id = kwargs.get("target_persona_id")
        actor_sheet = resolve_actor_sheet(actor)
        if actor_sheet is None or target_persona_id is None:
            return False, "Coerce whom?"
        target_persona = (
            Persona.objects.filter(pk=target_persona_id).select_related("character_sheet").first()
        )
        if target_persona is None:
            return False, "No such target."
        if has_leverage(holder_sheet=actor_sheet, subject_sheet=target_persona.character_sheet):
            return True, ""
        return False, "You hold no leverage over them."


def _is_visible_to(actor, target) -> bool:
    """Whether ``actor`` can perceive ``target``.

    Delegates to the real perception/concealment seam (#1225).
    """
    from world.conditions.services import can_perceive  # noqa: PLC0415

    return can_perceive(actor, target)


@dataclass
class ItemUsablePrerequisite(Prerequisite):
    """The item's template must have an on-use pool or appearance effects (usable);
    consumables must have charges remaining. Mirrors use_item's preconditions / #1026 is_usable."""

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
        if not template.is_usable and not template.appearance_effects.exists():
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


@dataclass
class IsShipOwnerPrerequisite(Prerequisite):
    """The actor's active persona must own the target ship (#1832).

    Resolves the ship from the ``ship`` (a ``ShipDetails`` instance) or
    ``ship_id`` kwarg (the kwargs-via-context convention) when present, else
    the ship whose room the actor stands in — ``ShipDetails`` whose
    building's ``entry_room`` is ``actor.location`` (a ship currently has
    exactly one room, the deck).

    Ownership is either direct (``ShipDetails.building.owner_persona`` — set
    for every commissioning persona regardless of covenant, see
    ``world.ships.services.complete_ship_construction``) or covenant-held
    (``is_owner`` walks the ship's entry room's ``LocationOwnership``
    cascade, set by ``transfer_ownership`` when a covenant is the
    deed-holder — covers any of its current members).
    """

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.locations.services import is_owner  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
        from world.ships.models import ShipDetails  # noqa: PLC0415

        kwargs = (context or {}).get("kwargs", {})
        ship = kwargs.get("ship")
        if ship is None:
            ship_id = kwargs.get("ship_id")
            if ship_id:
                ship = (
                    ShipDetails.objects.filter(pk=ship_id)
                    .select_related("building__entry_room")
                    .first()
                )
            else:
                room = actor.location
                ship = (
                    ShipDetails.objects.filter(building__entry_room__objectdb=room)
                    .select_related("building__entry_room")
                    .first()
                    if room is not None
                    else None
                )
        if ship is None:
            return False, "No such ship."
        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return False, ONLY_CHARACTERS_MESSAGE
        persona = active_persona_for_sheet(sheet)
        if ship.building.owner_persona_id == persona.pk:
            return True, ""
        entry_room = ship.building.entry_room
        if entry_room is not None and is_owner(persona, entry_room.objectdb):
            return True, ""
        return False, "You don't own this ship."


@dataclass
class HasCompanionCapacityPrerequisite(Prerequisite):
    """True if the actor has Companion Capacity remaining for one more companion.

    Reads gift_id/archetype_id straight from context["kwargs"] — the same
    convention IsShipOwnerPrerequisite and other action prerequisites use to
    read action-call kwargs before execute() runs.
    """

    def is_met(self, actor, target=None, context=None) -> tuple[bool, str]:
        from world.companions.models import CompanionArchetype  # noqa: PLC0415
        from world.companions.services import (  # noqa: PLC0415
            NoCompanionThreadError,
            companion_capacity,
            used_companion_capacity,
        )
        from world.magic.models.gifts import Gift  # noqa: PLC0415

        kwargs = (context or {}).get("kwargs", {})
        gift_id = kwargs.get("gift_id")
        archetype_id = kwargs.get("archetype_id")
        if not gift_id or not archetype_id:
            return False, "Pick a gift and an archetype first."
        try:
            gift = Gift.objects.get(pk=gift_id)
            archetype = CompanionArchetype.objects.get(pk=archetype_id)
        except (Gift.DoesNotExist, CompanionArchetype.DoesNotExist):
            return False, "No such gift or archetype."

        sheet = resolve_actor_sheet(actor)
        if sheet is None:
            return False, "You have no character sheet."
        try:
            remaining = companion_capacity(sheet, gift) - used_companion_capacity(sheet, gift)
        except NoCompanionThreadError:
            return False, "You don't have that gift's Companion Capacity available."
        if remaining < archetype.capacity_cost:
            return False, f"You don't have enough Companion Capacity to bind a {archetype.name}."
        return True, ""


@dataclass
class GhostWindowPrerequisite(Prerequisite):
    """Bound a dead character's emit/pose to recognized containers (#2287).

    Alive actors always pass. A dead actor passes while any container is
    open:

    - the scene they died in is still active and they are at its location,
    - an OPEN funeral honoring them is underway at their location (#2289), or
    - the current IC day matches the IC day of their death (real-day fallback
      when no game clock exists), or
    - an ACCEPTED seance offer whose ceremony is OPEN, at the ceremony's location (#2393).
    """

    def is_met(  # noqa: PLR0911
        self, actor, target=None, context=None
    ) -> tuple[bool, str]:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.ceremonies.services import open_funeral_for  # noqa: PLC0415
        from world.vitals.services import is_dead  # noqa: PLC0415

        try:
            sheet = actor.sheet_data
            vitals = sheet.vitals
        except (AttributeError, ObjectDoesNotExist):
            return True, ""
        if not is_dead(sheet):
            return True, ""
        scene = vitals.died_in_scene
        if scene is not None and scene.is_active and actor.location == scene.location:
            return True, ""
        funeral = open_funeral_for(sheet)
        if funeral is not None and actor.location == funeral.location.objectdb:
            return True, ""
        if _same_ic_day_as_now(vitals.died_at):
            return True, ""
        if _seance_container_open(actor, sheet):
            return True, ""
        return False, "The scene of your death has closed; your voice is spent."


def _same_ic_day_as_now(died_at: Any) -> bool:
    """True when ``died_at`` falls on the current IC day (#2287).

    Real-day comparison fallback when no game clock exists.
    """
    if died_at is None:
        return False
    from django.utils import timezone  # noqa: PLC0415

    from world.game_clock.services import (  # noqa: PLC0415
        get_ic_date_for_real_time,
        get_ic_now,
    )

    ic_now = get_ic_now()
    died_ic = get_ic_date_for_real_time(died_at)
    if ic_now is not None and died_ic is not None:
        return died_ic.date() == ic_now.date()
    return died_at.date() == timezone.now().date()


def _seance_container_open(actor: Any, sheet: Any) -> bool:
    """True when an ACCEPTED seance offer's ceremony is OPEN at the actor's location (#2393)."""
    from world.ceremonies.constants import CeremonyStatus, SeanceOfferStatus  # noqa: PLC0415
    from world.ceremonies.models import SeanceManifestationOffer  # noqa: PLC0415

    offer = (
        SeanceManifestationOffer.objects.filter(
            ceremony_honoree__honoree_sheet=sheet,
            status=SeanceOfferStatus.ACCEPTED,
            ceremony_honoree__ceremony__status=CeremonyStatus.OPEN,
        )
        .select_related("ceremony_honoree__ceremony__location")
        .first()
    )
    if offer is None:
        return False
    return actor.location == offer.ceremony_honoree.ceremony.location.objectdb
