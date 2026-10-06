"""Current typed room targets and bounded read-safe traversal checks."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from evennia.objects.models import ObjectDB

from actions.prerequisites import Prerequisite
from actions.target_menu_types import MenuTargetKind, MenuTargetRequest, ResolvedMenuTarget
from actions.target_resolution import resolve_menu_target
from actions.types import ActionContext, ActionResult
from behaviors.traversal_inspection import inspect_exit_traversal
from commands.exceptions import CommandError
from world.mechanics.constants import ChallengeType
from world.mechanics.models import ChallengeInstance
from world.scenes.models import Persona
from world.scenes.place_models import Place, PlacePresence
from world.scenes.services import active_persona_for_sheet

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from actions.base import Action
    from actions.models import ActionEnhancement
    from flows.scene_data_manager import SceneDataManager

MENU_TARGET_KEY = "menu_target"
TRAVERSE_EXIT_KEY = "traverse_exit"
UNAVAILABLE = "That isn't available."
COMPETING = frozenset(
    {
        "target",
        "target_id",
        "place",
        "place_id",
        "item",
        "item_id",
        "item_instance_id",
        "target_persona_id",
        "owner_persona_id",
        "container_item_id",
        "pending_inputs",
    }
)


def room_request(
    kwargs: dict[str, Any], kinds: frozenset[MenuTargetKind]
) -> MenuTargetRequest | None:
    """Parse a domain-qualified request without another source of identity."""
    if COMPETING.intersection(kwargs):
        return None
    wire = kwargs.get("menu_target")
    if not isinstance(wire, dict) or set(wire) != {"kind", "target_id"}:
        return None
    kind = next((kind for kind in kinds if wire["kind"] == kind.value), None)
    if kind is None or type(wire["target_id"]) is not int or wire["target_id"] <= 0:
        return None
    return MenuTargetRequest(kind, wire["target_id"])


def room_target(
    actor: ObjectDB | None, kwargs: dict[str, Any], kinds: frozenset[MenuTargetKind]
) -> ResolvedMenuTarget | None:
    """Resolve fresh scope; never return cached permission."""
    request = room_request(kwargs, kinds)
    return resolve_menu_target(actor, request) if request is not None else None


def current_persona(actor: ObjectDB | None) -> Persona | None:
    """Read the presented face or deny a broken primary invariant."""
    if actor is None:
        return None
    sheet = actor.character_sheet
    if sheet is None:
        return None
    try:
        return active_persona_for_sheet(sheet)
    except Persona.DoesNotExist:
        return None


def at_place(actor: ObjectDB | None, place: Place) -> bool:
    """Check only the current active persona's membership."""
    persona = current_persona(actor)
    return (
        persona is not None and PlacePresence.objects.filter(place=place, persona=persona).exists()
    )


def apply_room_enhancements(
    context: ActionContext,
    actor: ObjectDB | None,
    enhancements: list[ActionEnhancement] | None,
    apply: Callable[[ActionContext, ObjectDB | None, list[ActionEnhancement] | None], None],
    kinds: frozenset[MenuTargetKind],
) -> None:
    """Keep the original typed domain across existing enhancement application."""
    typed = MENU_TARGET_KEY in context.kwargs
    request = room_request(context.kwargs, kinds) if typed else None
    apply(context, actor, enhancements)
    if not typed:
        if MENU_TARGET_KEY in context.kwargs:
            context.kwargs["menu_target"] = None
        return
    updated = room_request(context.kwargs, kinds)
    if request is None or updated is None or request.kind is not updated.kind:
        context.kwargs["menu_target"] = None


def emit_room_intent(
    context: ActionContext,
    actor: ObjectDB | None,
    emit: Callable[[ActionContext, ObjectDB | None], ActionResult | None],
    kinds: frozenset[MenuTargetKind],
) -> ActionResult | None:
    """Adapt one existing intent; redirect within the original explicit domain."""
    if actor is None or MENU_TARGET_KEY not in context.kwargs:
        return emit(context, actor)
    request = room_request(context.kwargs, kinds)
    if request is None:
        cancelled = emit(context, actor)
        context.kwargs.pop("target", None)
        context.kwargs["menu_target"] = None
        return cancelled
    resolved = room_target(actor, context.kwargs, kinds)
    original = (
        None
        if resolved is None
        else (resolved.place if request.kind is MenuTargetKind.PLACES else resolved.game_object)
    )
    original_wire = dict(context.kwargs["menu_target"])
    context.kwargs["target"] = original
    cancelled = emit(context, actor)
    redirected = context.kwargs.pop("target", None)
    if cancelled is not None:
        return cancelled
    changed_wire = context.kwargs.get("menu_target") != original_wire
    if redirected is original:
        updated = room_request(context.kwargs, kinds)
        if updated is None or updated.kind is not request.kind:
            context.kwargs["menu_target"] = None
        return None
    if changed_wire:
        context.kwargs["menu_target"] = None
        return None
    model = Place if request.kind is MenuTargetKind.PLACES else ObjectDB
    if type(redirected) is int and redirected > 0:
        redirected = model.objects.filter(pk=redirected).first()
    if not isinstance(redirected, model):
        context.kwargs["menu_target"] = None
        return None
    context.kwargs["menu_target"] = {"kind": request.kind.value, "target_id": redirected.pk}
    return None


def blocking_exit_challenges(exit_obj: ObjectDB) -> QuerySet[ChallengeInstance]:
    """Retain only existing active revealed inhibitors."""
    return ChallengeInstance.objects.filter(
        location=exit_obj,
        is_active=True,
        is_revealed=True,
        template__challenge_type=ChallengeType.INHIBITOR,
    ).select_related("template")


def room_target_refusal(
    action: Action,
    actor: ObjectDB | None,
    kwargs: dict[str, Any],
    *,
    scene_data: SceneDataManager | None = None,
) -> str | None:
    """Return the action-owned current refusal without constructing flow states."""
    if not action.is_applicable(actor, kwargs=kwargs):
        return UNAVAILABLE
    resolved = room_target(actor, kwargs, action.menu_kinds)
    if resolved is None:
        return UNAVAILABLE
    if action.key == TRAVERSE_EXIT_KEY:
        if resolved.game_object is None:
            return UNAVAILABLE
        if blocking_exit_challenges(resolved.game_object).exists():
            return "The way is blocked."
        try:
            inspect_exit_traversal(actor, resolved.game_object, scene_data=scene_data)
        except CommandError as error:
            return str(error)
        fresh = room_target(actor, kwargs, action.menu_kinds)
        if fresh is None or fresh.game_object != resolved.game_object:
            return UNAVAILABLE
    return None


class RoomTargetPrerequisite(Prerequisite):
    """Keep typed fit and complete availability inside the owning action."""

    def __init__(self, action: Action) -> None:
        self.action = action

    def is_met(
        self,
        actor: ObjectDB | None,
        target: ObjectDB | None = None,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        kwargs = dict((context or {}).get("kwargs", {}))
        if MENU_TARGET_KEY not in kwargs:
            return True, ""
        reason = room_target_refusal(
            self.action, actor, kwargs, scene_data=(context or {}).get("scene_data")
        )
        return reason is None, reason or ""
