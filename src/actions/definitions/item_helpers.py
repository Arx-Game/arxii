"""Shared helpers for item-related actions.

Resolve an explicitly typed ItemInstance or a legacy ObjectDB target to the
item used by inventory services. Resolution does not grant permission to act.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from evennia.objects.models import ObjectDB

from actions.target_menu_types import MenuTargetKind, MenuTargetRequest, ResolvedMenuTarget
from actions.target_resolution import resolve_menu_target
from actions.types import ActionContext, ActionResult
from world.items.models import ItemInstance


def resolve_item_instance(target: ObjectDB | ItemInstance | None) -> ItemInstance | None:
    """Return the item represented by an explicitly typed target.

    This helper does not resolve integer IDs or authorize an operation.

    Args:
        target: A resolved object, an item instance, or no target.

    Returns:
        The explicit item or the object's related item, otherwise None.
    """
    if isinstance(target, ItemInstance):
        return target
    if not isinstance(target, ObjectDB):
        return None
    try:
        return target.item_instance
    except ObjectDB.item_instance.RelatedObjectDoesNotExist:  # type: ignore[attr-defined]
        return None


MENU_TARGET_KEY = "menu_target"
_TARGET_ID_KEY = "target_id"
_OWNER_PERSONA_ID_KEY = "owner_persona_id"
_CONTAINER_ITEM_ID_KEY = "container_item_id"

_TYPED_ITEM_LEGACY_FIELDS = frozenset(
    {
        "target",
        "target_id",
        "item",
        "item_id",
        "item_instance_id",
        "item_name",
        "owner_id",
        "container_id",
        "target_persona_id",
        "owner_persona_id",
        "container_item_id",
    }
)
_TYPED_ITEM_WIRE_FIELDS = frozenset({"kind", "target_id", "owner_persona_id", "container_item_id"})


def typed_item_request(kwargs: dict[str, Any]) -> MenuTargetRequest | None:
    """Parse a strict typed item request without competing legacy targets."""
    if _TYPED_ITEM_LEGACY_FIELDS.intersection(kwargs):
        return None
    wire = kwargs.get("menu_target")
    if not isinstance(wire, dict) or set(wire).difference(_TYPED_ITEM_WIRE_FIELDS):
        return None
    if wire.get("kind") != MenuTargetKind.ITEMS.value or _TARGET_ID_KEY not in wire:
        return None
    for name in ("target_id", "owner_persona_id", "container_item_id"):
        if name in wire and (type(wire[name]) is not int or wire[name] <= 0):
            return None
    if _OWNER_PERSONA_ID_KEY in wire and _CONTAINER_ITEM_ID_KEY in wire:
        return None
    return MenuTargetRequest(
        MenuTargetKind.ITEMS,
        wire["target_id"],
        owner_persona_id=wire.get("owner_persona_id"),
        container_item_id=wire.get("container_item_id"),
    )


def resolve_typed_item(actor: ObjectDB, kwargs: dict[str, Any]) -> ResolvedMenuTarget | None:
    """Resolve current readable item scope without retaining permission."""
    request = typed_item_request(kwargs)
    if request is None:
        return None
    resolved = resolve_menu_target(actor, request)
    return resolved if resolved is not None and resolved.item is not None else None


def emit_typed_item_intent(
    context: ActionContext,
    actor: ObjectDB | None,
    emit: Callable[[ActionContext, ObjectDB | None], ActionResult | None],
) -> ActionResult | None:
    """Adapt typed item intent, preserving asserted scope on redirects."""
    if actor is None or MENU_TARGET_KEY not in context.kwargs:
        return emit(context, actor)
    request = typed_item_request(context.kwargs)
    if request is None:
        return emit(context, actor)
    resolved = resolve_typed_item(actor, context.kwargs)
    original = resolved.game_object if resolved is not None else None
    context.kwargs["target"] = original
    cancelled = emit(context, actor)
    redirected = context.kwargs.pop("target")
    if cancelled is not None:
        return cancelled
    if redirected is original:
        return None
    if type(redirected) is int and redirected > 0:
        redirected = ObjectDB.objects.filter(pk=redirected).first()
    if not isinstance(redirected, ObjectDB):
        context.kwargs["menu_target"] = None
        return None
    item = resolve_item_instance(redirected)
    if item is None:
        context.kwargs["menu_target"] = None
        return None
    wire = {"kind": request.kind.value, "target_id": item.pk}
    if request.owner_persona_id is not None:
        wire["owner_persona_id"] = request.owner_persona_id
    if request.container_item_id is not None:
        wire["container_item_id"] = request.container_item_id
    context.kwargs["menu_target"] = wire
    return None
