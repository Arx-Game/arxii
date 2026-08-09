"""Perception-related actions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType
from flows.scene_data_manager import SceneDataManager

if TYPE_CHECKING:
    from world.items.models import ItemInstance


def _resolve_look_target(kwargs: dict[str, Any]) -> ObjectDB | None:
    """Resolve the look target from either dispatch shape (#3044).

    Telnet passes an already-resolved ``target`` ``ObjectDB`` directly. The
    web room-objects panel's examine-on-click affordance sends a raw ``target``
    kwarg holding the object's pk (an ``int``) — REST dispatch
    (``dispatch_player_action`` -> ``_dispatch_registry``) does no ``ObjectDB``
    resolution of its own; ``objectdb_target_kwargs`` only helps the *websocket*
    inputfunc. Resolve defensively here so both dispatch shapes work, mirroring
    ``_resolve_identify_target`` (``actions/definitions/identification.py``) and
    ``_resolve_room`` (``actions/definitions/locations.py``).
    """
    target = kwargs.get("target")
    if target is None or isinstance(target, ObjectDB):
        return target
    return ObjectDB.objects.filter(pk=target).first()


@dataclass
class LookAction(Action):
    """Look at a target entity to get its description."""

    key: str = "look"
    name: str = "Look"
    icon: str = "eye"
    category: str = "perception"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = "before_look"
    result_event: str | None = "look"

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = _resolve_look_target(kwargs)
        if target is None:
            return ActionResult(success=False, message="Look at what?")

        # #1225: gate direct look-at-target on the real perception/concealment seam.
        # The bare-``look`` case (target is the room itself) and looking at oneself
        # are exempt — ``can_perceive``'s co-location check assumes an occupant/held
        # item, not the room container, and a looker always perceives themselves
        # regardless of their own concealment (mirrors ``get_display_characters``).
        if target not in (actor.location, actor):
            from world.conditions.services import can_perceive  # noqa: PLC0415

            if not can_perceive(actor, target):
                # Deliberately the same not-found idiom ``CmdLook`` uses for a failed
                # search (``f"Could not find '{args}'."``) — a concealed-and-undetected
                # target must be indistinguishable from a genuinely absent one.
                return ActionResult(success=False, message=f"Could not find '{target.key}'.")

        # #2287: an unconscious looker's perception is dreamside — looking at
        # "the room" shows the dream space, not the waking one.
        if target == actor.location:
            from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

            from world.dreams.services import dreamspace_for  # noqa: PLC0415
            from world.vitals.services import perceives_dreamside  # noqa: PLC0415

            try:
                sheet = actor.sheet_data
            except (AttributeError, ObjectDoesNotExist):
                sheet = None
            if perceives_dreamside(sheet):
                target = dreamspace_for(sheet) or target

        sdm = context.scene_data if context else SceneDataManager()
        target_state = sdm.initialize_state_for_object(target)
        looker_state = sdm.initialize_state_for_object(actor)
        description = target_state.return_appearance(mode="look", looker=looker_state)

        # #3044 — the mission ENVIRONMENTAL_DETAIL/BOARD dispatch hook lives on
        # ``ObjectParent.at_examined`` (`typeclasses/mixins.py`), which fires from
        # the TYPECLASS's own ``return_appearance``. Nothing in the live look
        # pipeline calls that: this Action (shared by telnet's ``CmdLook`` and the
        # web dispatch) renders through the flows-layer ``BaseState.return_appearance``
        # instead, which never touches the typeclass hook — so examine-triggered
        # mission dispatch was unreachable from real play on either surface, only
        # from tests that call the service directly. Dispatch it explicitly here,
        # the one seam both telnet and web now share. ``run_safely`` (#1164): a
        # failure is captured + the examiner told, never breaking the look.
        from world.missions.services.trigger_dispatch import (  # noqa: PLC0415
            maybe_dispatch_on_examine,
        )
        from world.player_submissions.services import run_safely  # noqa: PLC0415

        run_safely(
            "mission_dispatch_on_examine",
            lambda: maybe_dispatch_on_examine(actor, target),
            actor=actor,
        )

        return ActionResult(
            success=True,
            message=description,
        )


@dataclass
class LookAtItemAction(Action):
    """Examine a specific item — either worn on a character or in a container.

    Dispatched by ``CmdLook`` when the player uses one of the drilled forms:
    ``look bob's hat``, ``look hat on bob``, or ``look coin in pouch``.

    Visibility for worn items is enforced via
    :func:`world.items.services.appearance.visible_worn_items_for` — concealed
    items are hidden from non-self / non-staff observers. Closed containers
    refuse to reveal their contents.
    """

    key: str = "look_at_item"
    name: str = "Examine Item"
    icon: str = "eye"
    category: str = "perception"
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        item_name = kwargs.get("item_name")
        owner_id = kwargs.get("owner_id")
        container_id = kwargs.get("container_id")

        if not item_name:
            return ActionResult(success=False, message="Look at what?")

        if owner_id is None and container_id is None:
            return ActionResult(success=False, message="Look at what?")

        if owner_id is not None:
            return self._look_at_worn(actor, owner_id, item_name)

        return self._look_at_contained(actor, container_id, item_name)

    def _look_at_worn(
        self,
        actor: ObjectDB,
        owner_id: int,
        item_name: str,
    ) -> ActionResult:
        from world.items.services.appearance import (  # noqa: PLC0415
            visible_worn_items_for,
        )

        try:
            owner = ObjectDB.objects.get(pk=owner_id)
        except ObjectDB.DoesNotExist:
            return ActionResult(success=False, message="They aren't here.")

        visible = visible_worn_items_for(owner, observer=actor)
        item = self._find_by_name(
            visible,
            item_name,
            key=lambda v: v.item_instance,
        )
        if item is None:
            return ActionResult(
                success=False,
                message=f"You don't see anything by that name on {owner.key}.",
            )

        return ActionResult(success=True, message=self._render_item(item))

    def _look_at_contained(
        self,
        actor: ObjectDB,
        container_id: int,
        item_name: str,
    ) -> ActionResult:
        from core_management.permissions import is_staff_observer  # noqa: PLC0415
        from flows.object_states.item_state import ItemState  # noqa: PLC0415

        try:
            container_obj = ObjectDB.objects.get(pk=container_id)
        except ObjectDB.DoesNotExist:
            return ActionResult(success=False, message="That isn't here.")

        try:
            container_instance = container_obj.item_instance
        except ObjectDB.item_instance.RelatedObjectDoesNotExist:  # type: ignore[attr-defined]
            return ActionResult(success=False, message="That isn't a container.")

        # Reach gate: clients can POST any container pk via the action
        # dispatcher. Without this check, an actor could read the contents
        # of any open container in the database. Staff bypass mirrors the
        # rest of the look pipeline (concealed worn items, etc.).
        if not is_staff_observer(actor):
            sdm = SceneDataManager()
            container_state = ItemState(container_instance, context=sdm)
            if not container_state.is_reachable_by(actor):
                return ActionResult(success=False, message="That isn't here.")

        if container_instance.template.supports_open_close and not container_instance.is_open:
            return ActionResult(success=False, message="That container is closed.")

        contents = list(container_instance.contents.all())
        item = self._find_by_name(contents, item_name)
        if item is None:
            container_label = container_instance.display_name
            return ActionResult(
                success=False,
                message=(f"You don't see anything by that name in the {container_label}."),
            )

        return ActionResult(success=True, message=self._render_item(item))

    @staticmethod
    def _find_by_name(
        items: list[Any],
        name: str,
        key: Callable[[Any], ItemInstance] = lambda x: x,
    ) -> ItemInstance | None:
        """Case-insensitive search by display_name. Returns None on miss."""
        target = name.lower().strip()
        for entry in items:
            instance = key(entry)
            if instance.display_name.lower() == target:
                return instance
        # Substring fallback
        for entry in items:
            instance = key(entry)
            if target in instance.display_name.lower():
                return instance
        return None

    @staticmethod
    def _render_item(item: ItemInstance) -> str:
        """Format the item appearance for the look output."""
        return f"{item.display_name}\n{item.display_description}"


@dataclass
class InventoryAction(Action):
    """View the character's inventory."""

    key: str = "inventory"
    name: str = "Inventory"
    icon: str = "backpack"
    category: str = "perception"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        sdm = context.scene_data if context else SceneDataManager()
        caller_state = sdm.initialize_state_for_object(actor)
        items = caller_state.contents
        burden = _burden_line(actor)
        if not items:
            text = "You are not carrying anything."
            return ActionResult(success=True, message=f"{text}\n{burden}" if burden else text)

        names = [it.get_display_name(looker=caller_state) for it in items]
        text = "You are carrying: " + ", ".join(names)
        if burden:
            text = f"{text}\n{burden}"
        return ActionResult(success=True, message=text)


def _burden_line(actor: ObjectDB) -> str:
    """How heavily laden the character is (#2862 gap close).

    Encumbrance was previously invisible — a player only learned of it by
    being told the load dragged at them, with no way to see how close the
    wall was. Silent when unladen, since being under capacity costs nothing
    and needs no commentary.
    """
    from world.items.services.encumbrance import (  # noqa: PLC0415
        EncumbranceBand,
        carried_load,
        carry_capacity,
        encumbrance_band,
    )

    band = encumbrance_band(actor)
    if band is EncumbranceBand.FREE:
        return ""
    load = carried_load(actor)
    capacity = carry_capacity(actor)
    if band is EncumbranceBand.ENCUMBERED:
        return f"|yYou are laden ({load}/{capacity}) — moving will tire you.|n"
    return (
        f"|rYou are massively overloaded ({load}/{capacity}) — every step costs "
        "dearly, and if you tire out you will not be able to move at all.|n"
    )
