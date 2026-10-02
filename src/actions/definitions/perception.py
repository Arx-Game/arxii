"""Perception-related actions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.prerequisites import Prerequisite
from actions.target_menu_types import MenuTargetKind, MenuTargetRequest, ResolvedMenuTarget
from actions.target_resolution import resolve_menu_target, resolve_persona_pk_to_character
from actions.types import ActionContext, ActionResult, TargetType
from flows.scene_data_manager import SceneDataManager

if TYPE_CHECKING:
    from typeclasses.types import ArxTypeclass
    from world.items.models import ItemInstance

_LOOK_AT_WHAT_MESSAGE = "Look at what?"
LOOK_NOT_VISIBLE_MESSAGE = "You can't see them from here."


def look_target_visible(actor: ObjectDB, target: ObjectDB) -> bool:
    """Whether *actor* may look at *target* right now (#4030).

    True for the actor's own location (the bare-``look`` case) and for looking at
    themself — ``can_perceive``'s co-location check assumes an occupant/held item,
    not the room container, and a looker always perceives themselves regardless of
    their own concealment (mirrors ``get_display_characters``). Otherwise delegates
    to the real perception/concealment seam, ``can_perceive`` (#1225).

    The single source of the Look visibility rule — ``LookAction.execute()`` and
    the persona menu (``actions.persona_menu``) both call this so the two never
    drift (#4030 review: the persona menu had hand-copied a near-identical but
    not-quite-identical condition).
    """
    if target in (actor.location, actor):
        return True
    from world.conditions.services import can_perceive  # noqa: PLC0415

    return can_perceive(actor, target)


def _resolve_look_target(kwargs: dict[str, Any]) -> ObjectDB | None:
    """Resolve the look target from any dispatch shape (#3044, #4030).

    - Telnet passes an already-resolved ``target`` ``ObjectDB``.
    - The web room-objects panel sends ``target`` as an object pk (an ``int``).
    - The web persona menu sends ``target_persona_id`` (a ``Persona`` pk); it resolves
      to the character underneath through ``actions.target_resolution``. The perception
      gate and masked-name rendering in ``execute()`` still apply unchanged.
    REST dispatch does no ``ObjectDB`` resolution of its own, so resolve here.
    """
    target = kwargs.get("target")
    if isinstance(target, ObjectDB):
        return target
    if target is not None:
        return ObjectDB.objects.filter(pk=target).first()
    return resolve_persona_pk_to_character(kwargs.get("target_persona_id"))


def _render_physical_look(
    actor: ObjectDB,
    target: ObjectDB,
    context: ActionContext | None,
) -> ActionResult:
    """Render one authorized deliberate physical Look with existing extras."""
    sdm = context.scene_data if context else SceneDataManager()
    target_state = sdm.initialize_state_for_object(cast("ArxTypeclass", target))
    looker_state = sdm.initialize_state_for_object(cast("ArxTypeclass", actor))
    description = target_state.return_appearance(mode="look", looker=cast(Any, looker_state))
    from actions.definitions.examine_extras import gather_examine_extras  # noqa: PLC0415

    extras = gather_examine_extras(actor, target)
    if extras.cancelled:
        return ActionResult(success=True, message="")
    if extras.sections:
        description = f"{description}\n" + "\n".join(extras.sections)
    return ActionResult(success=True, message=description)


@dataclass
class LookAction(Action):
    """Look at a target entity to get its description."""

    key: str = "look"
    name: str = "Look"
    icon: str = "eye"
    category: str = "perception"
    target_type: TargetType = TargetType.SINGLE

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = _resolve_look_target(kwargs)
        if target is None:
            return ActionResult(success=False, message=_LOOK_AT_WHAT_MESSAGE)

        # #4030: a ``target_persona_id`` dispatch (the persona menu) never had a real
        # ObjectDB/pk on the wire, only the persona the viewer sees — which may be a
        # mask. Telnet and the pk-based ``target`` shape already resolved a genuine
        # ObjectDB the caller could see, so their refusal text is safe to keep as-is.
        via_persona_id = kwargs.get("target") is None

        # #1225: gate direct look-at-target on the real perception/concealment seam.
        # The bare-``look`` case (target is the room itself) and looking at oneself
        # are exempt — ``can_perceive``'s co-location check assumes an occupant/held
        # item, not the room container, and a looker always perceives themselves
        # regardless of their own concealment (mirrors ``get_display_characters``).
        if not look_target_visible(actor, target):
            if via_persona_id:
                # #4030: never name the real character key behind a mask —
                # a persona-id look can target someone concealed, or simply
                # not co-located, and either way the real identity must stay
                # hidden, not just indistinguishable-from-absent.
                return ActionResult(success=False, message=LOOK_NOT_VISIBLE_MESSAGE)
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

        return _render_physical_look(actor, target, context)


ITEM_LOOK_UNAVAILABLE_MESSAGE = "That isn't available to look at."
_ITEM_LOOK_MENU_TARGET_KEY = "menu_target"
_ITEM_LOOK_KIND_KEY = "kind"
_ITEM_LOOK_TARGET_ID_KEY = "target_id"
_ITEM_LOOK_OWNER_PERSONA_ID_KEY = "owner_persona_id"
_ITEM_LOOK_CONTAINER_ITEM_ID_KEY = "container_item_id"
_ITEM_LOOK_LEGACY_FIELDS = frozenset(
    {
        "target",
        _ITEM_LOOK_TARGET_ID_KEY,
        "item",
        "item_id",
        "item_instance_id",
        "item_name",
        "owner_id",
        "container_id",
        "target_persona_id",
        _ITEM_LOOK_OWNER_PERSONA_ID_KEY,
        _ITEM_LOOK_CONTAINER_ITEM_ID_KEY,
    }
)
_ITEM_LOOK_WIRE_FIELDS = frozenset(
    {
        _ITEM_LOOK_KIND_KEY,
        _ITEM_LOOK_TARGET_ID_KEY,
        _ITEM_LOOK_OWNER_PERSONA_ID_KEY,
        _ITEM_LOOK_CONTAINER_ITEM_ID_KEY,
    }
)


def _item_look_request(kwargs: dict[str, Any]) -> MenuTargetRequest | None:
    """Parse this action's typed wire input without guessing an ID domain."""
    if _ITEM_LOOK_LEGACY_FIELDS.intersection(kwargs):
        return None
    wire = kwargs.get(_ITEM_LOOK_MENU_TARGET_KEY)
    if not isinstance(wire, dict) or set(wire).difference(_ITEM_LOOK_WIRE_FIELDS):
        return None
    if wire.get(_ITEM_LOOK_KIND_KEY) != MenuTargetKind.ITEMS.value:
        return None
    if _ITEM_LOOK_TARGET_ID_KEY not in wire:
        return None
    for name in (
        _ITEM_LOOK_TARGET_ID_KEY,
        _ITEM_LOOK_OWNER_PERSONA_ID_KEY,
        _ITEM_LOOK_CONTAINER_ITEM_ID_KEY,
    ):
        if name in wire and (type(wire[name]) is not int or wire[name] <= 0):
            return None
    if _ITEM_LOOK_OWNER_PERSONA_ID_KEY in wire and _ITEM_LOOK_CONTAINER_ITEM_ID_KEY in wire:
        return None
    return MenuTargetRequest(
        kind=MenuTargetKind.ITEMS,
        target_id=wire[_ITEM_LOOK_TARGET_ID_KEY],
        owner_persona_id=wire.get(_ITEM_LOOK_OWNER_PERSONA_ID_KEY),
        container_item_id=wire.get(_ITEM_LOOK_CONTAINER_ITEM_ID_KEY),
    )


def _resolve_item_look(actor: ObjectDB, kwargs: dict[str, Any]) -> ResolvedMenuTarget | None:
    """Return this viewer's current authorized item, not cached permission."""
    request = _item_look_request(kwargs)
    if request is None:
        return None
    resolved = resolve_menu_target(actor, request)
    if resolved is None or resolved.item is None:
        return None
    return resolved


@dataclass
class _TypedItemLookPrerequisite(Prerequisite):
    """Share typed item visibility between read checks and execution."""

    def is_met(self, actor, target=None, context=None):
        kwargs = (context or {}).get("kwargs", {})
        if _ITEM_LOOK_MENU_TARGET_KEY not in kwargs:
            return True, ""
        if _resolve_item_look(actor, kwargs) is None:
            return False, ITEM_LOOK_UNAVAILABLE_MESSAGE
        return True, ""


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
        if _ITEM_LOOK_MENU_TARGET_KEY in kwargs:
            resolved = _resolve_item_look(actor, kwargs)
            if resolved is None:
                return ActionResult(success=False, message=ITEM_LOOK_UNAVAILABLE_MESSAGE)
            if resolved.game_object is not None:
                return _render_physical_look(actor, resolved.game_object, context)
            assert resolved.item is not None  # noqa: S101
            return ActionResult(success=True, message=self._render_item(resolved.item))

        item_name = kwargs.get("item_name")
        owner_id = kwargs.get("owner_id")
        container_id = kwargs.get("container_id")

        if not item_name:
            return ActionResult(success=False, message=_LOOK_AT_WHAT_MESSAGE)

        if owner_id is None and container_id is None:
            return ActionResult(success=False, message=_LOOK_AT_WHAT_MESSAGE)

        if owner_id is not None:
            return self._look_at_worn(actor, owner_id, item_name)

        assert container_id is not None  # noqa: S101
        return self._look_at_contained(actor, container_id, item_name)

    def get_prerequisites(self) -> list[Prerequisite]:
        return [*super().get_prerequisites(), _TypedItemLookPrerequisite()]

    def _emit_intent(self, context: ActionContext, actor: ObjectDB | None) -> ActionResult | None:
        """Adapt typed item intent and retain the base interception lifecycle."""
        if actor is None or _ITEM_LOOK_MENU_TARGET_KEY not in context.kwargs:
            return super()._emit_intent(context, actor)
        request = _item_look_request(context.kwargs)
        if request is None:
            return super()._emit_intent(context, actor)
        resolved = _resolve_item_look(actor, context.kwargs)
        original = resolved.game_object if resolved is not None else None
        context.kwargs["target"] = original
        cancelled = super()._emit_intent(context, actor)
        redirected = context.kwargs.pop("target")
        if cancelled is not None:
            return cancelled
        if redirected is original:
            return None
        if type(redirected) is int and redirected > 0:
            redirected = ObjectDB.objects.filter(pk=redirected).first()
        if not isinstance(redirected, ObjectDB):
            context.kwargs[_ITEM_LOOK_MENU_TARGET_KEY] = None
            return None
        try:
            item = redirected.item_instance
        except ObjectDB.item_instance.RelatedObjectDoesNotExist:
            context.kwargs[_ITEM_LOOK_MENU_TARGET_KEY] = None
            return None
        wire = {
            _ITEM_LOOK_KIND_KEY: MenuTargetKind.ITEMS.value,
            _ITEM_LOOK_TARGET_ID_KEY: item.pk,
        }
        if request.owner_persona_id is not None:
            wire[_ITEM_LOOK_OWNER_PERSONA_ID_KEY] = request.owner_persona_id
        if request.container_item_id is not None:
            wire[_ITEM_LOOK_CONTAINER_ITEM_ID_KEY] = request.container_item_id
        context.kwargs[_ITEM_LOOK_MENU_TARGET_KEY] = wire
        return None

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
        except ObjectDB.item_instance.RelatedObjectDoesNotExist:
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
        """Format the item appearance for the look output.

        Appends the item-scoped provenance/catering subset (#3084) so a drilled
        worn/container look (``look hat on bob``, ``look coin in pouch``) shows the
        same sections a direct ``look`` at the item would include.
        """
        text = f"{item.display_name}\n{item.display_description}"

        from actions.definitions.examine_extras import (  # noqa: PLC0415
            _maybe_render_catering_history,
            _maybe_render_crafted_provenance,
        )

        game_object = item.game_object
        if game_object is not None:
            provenance = _maybe_render_crafted_provenance(game_object)
            if provenance is not None:
                text = f"{text}\n{provenance}"
            catering = _maybe_render_catering_history(game_object)
            if catering is not None:
                text = f"{text}\n{catering}"
        return text


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
        caller_state = sdm.initialize_state_for_object(cast("ArxTypeclass", actor))
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
