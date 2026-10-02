"""Resolve typed action/menu identities without granting permission to act.

Persona resolution retains the shared persona-to-character hop. Menu resolution
additionally checks the viewer's readable scope; actions still enforce their rules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q

from actions.target_menu_types import MenuTargetKind, MenuTargetRequest, ResolvedMenuTarget
from world.conditions.services import can_perceive
from world.items.models import ItemInstance

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def resolve_persona_pk_to_character(persona_id: object) -> ObjectDB | None:
    """Return the character behind the ``Persona`` with pk ``persona_id``, or ``None``."""
    from world.scenes.models import Persona  # noqa: PLC0415

    if persona_id is None:
        return None
    try:
        persona = (
            Persona.objects.filter(pk=persona_id)
            .select_related("character_sheet__character")
            .first()
        )
    except (TypeError, ValueError):
        return None
    if persona is None:
        return None
    return persona.character_sheet.character


def resolve_menu_target(
    actor: ObjectDB,
    request: MenuTargetRequest,
) -> ResolvedMenuTarget | None:
    """Resolve a supported target in the actor's current readable scope.

    Args:
        actor: The server-selected viewing character.
        request: A typed ID and any asserted owner/container context.

    Returns:
        The readable item, or None for unsupported or unavailable targets.
    """
    if not isinstance(request.kind, MenuTargetKind):
        return None
    if type(request.target_id) is not int or request.target_id <= 0:
        return None
    if request.owner_persona_id is not None or request.container_item_id is not None:
        return None
    if request.kind is MenuTargetKind.ITEMS:
        return _resolve_menu_item(actor, request)
    return None


def _resolve_menu_item(
    actor: ObjectDB,
    request: MenuTargetRequest,
) -> ResolvedMenuTarget | None:
    """Resolve an uncontained owned row or perceptible carried/room item."""
    scope = Q(game_object__db_location=actor)
    room = actor.location
    if room is not None:
        scope |= Q(game_object__db_location=room)
    sheet = actor.character_sheet
    if sheet is not None:
        scope |= Q(game_object__isnull=True, holder_character_sheet=sheet)
    item = (
        ItemInstance.objects.in_play()
        .filter(scope, pk=request.target_id, contained_in__isnull=True)
        .select_related("template", "game_object")
        .first()
    )
    if item is None:
        return None
    game_object = item.game_object
    if game_object is not None and not can_perceive(actor, game_object):
        return None
    return ResolvedMenuTarget(
        request=request,
        label=item.display_name,
        item=item,
        game_object=game_object,
    )
