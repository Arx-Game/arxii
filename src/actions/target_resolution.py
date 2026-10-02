"""Resolve typed action/menu identities without granting permission to act.

Persona resolution retains the shared persona-to-character hop. Menu resolution
additionally checks the viewer's readable scope; actions still enforce their rules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q

from actions.target_menu_types import MenuTargetKind, MenuTargetRequest, ResolvedMenuTarget
from flows.object_states.base_state import project_display_name
from flows.service_functions.serializers.room_state import exit_hidden_from_viewer
from world.conditions.services import can_perceive, passes_concealment_check
from world.items.models import EquippedItem, ItemInstance
from world.items.services.appearance import visible_worn_items_for
from world.scenes.models import Persona
from world.scenes.place_services import active_places
from world.scenes.services import active_persona_for_sheet

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


# Keep typed context rejection and existing ITEMS routing explicit at this boundary.
def resolve_menu_target(  # noqa: C901
    actor: ObjectDB,
    request: MenuTargetRequest,
) -> ResolvedMenuTarget | None:
    """Resolve a supported target in the actor's current readable scope.

    Args:
        actor: The server-selected viewing character.
        request: A typed ID and any asserted owner/container context.

    Returns:
        The readable target, or None for unsupported or unavailable targets.
    """
    if not isinstance(request.kind, MenuTargetKind):
        return None
    if type(request.target_id) is not int or request.target_id <= 0:
        return None
    if request.kind is not MenuTargetKind.ITEMS:
        if request.owner_persona_id is not None or request.container_item_id is not None:
            return None
        if request.kind is MenuTargetKind.PLACES:
            return _resolve_menu_place(actor, request)
        if request.kind in (MenuTargetKind.OBJECTS, MenuTargetKind.EXITS):
            return _resolve_room_menu_object(actor, request)
        return None
    if request.container_item_id is not None:
        if request.owner_persona_id is not None:
            return None
        if type(request.container_item_id) is not int or request.container_item_id <= 0:
            return None
        return _resolve_contained_menu_item(actor, request)
    if request.owner_persona_id is not None:
        if type(request.owner_persona_id) is not int or request.owner_persona_id <= 0:
            return None
        return _resolve_worn_menu_item(actor, request)
    return _resolve_menu_item(actor, request)


def _resolve_worn_menu_item(
    actor: ObjectDB,
    request: MenuTargetRequest,
) -> ResolvedMenuTarget | None:
    """Resolve exposed equipment under a current public owner assertion."""
    persona = Persona.objects.filter(pk=request.owner_persona_id).first()
    if persona is None:
        return None
    sheet = persona.character_sheet
    if active_persona_for_sheet(sheet) != persona:
        return None
    wearer = sheet.character
    room = actor.location
    if room is None or wearer.location != room:
        return None
    if actor.pk != wearer.pk and not can_perceive(actor, wearer):
        return None

    item = (
        ItemInstance.objects.in_play()
        .filter(
            pk=request.target_id,
            holder_character_sheet=sheet,
            contained_in__isnull=True,
        )
        .select_related("template", "game_object")
        .first()
    )
    if item is None:
        return None
    if not EquippedItem.objects.filter(character=sheet, item_instance=item).exists():
        return None
    game_object = item.game_object
    if game_object is not None and (
        game_object.location != wearer or not passes_concealment_check(actor, game_object)
    ):
        return None
    if not any(
        row.item_instance.pk == item.pk for row in visible_worn_items_for(wearer, observer=actor)
    ):
        return None
    return ResolvedMenuTarget(
        request=request,
        label=item.display_name,
        item=item,
        game_object=game_object,
    )


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


# Keep kind, perception and attached-item checks together before projecting a label.
def _resolve_room_menu_object(  # noqa: C901, PLR0912
    actor: ObjectDB,
    request: MenuTargetRequest,
) -> ResolvedMenuTarget | None:
    """Resolve an ordinary room object or exit by its ObjectDB identity."""
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    room = actor.location
    if room is None or not room.is_typeclass("typeclasses.rooms.Room", exact=False):
        return None
    game_object = ObjectDB.objects.filter(
        pk=request.target_id, db_location=room,
    ).first()
    if game_object is None:
        return None
    if request.kind is MenuTargetKind.EXITS:
        if not game_object.is_typeclass("typeclasses.exits.Exit", exact=False):
            return None
        if not can_perceive(actor, game_object):
            return None
        if exit_hidden_from_viewer(game_object, actor):
            return None
        item = None
    else:
        # Reject identity-bearing/sibling types even with multiple inheritance.
        if any(
            game_object.is_typeclass(path, exact=False)
            for path in (
                "typeclasses.characters.Character",
                "typeclasses.rooms.Room",
                "typeclasses.exits.Exit",
            )
        ):
            return None
        if not game_object.is_typeclass("typeclasses.objects.Object", exact=False):
            return None
        if not can_perceive(actor, game_object):
            return None
        # Use the real one-to-one relation; no cross-domain integer conversion.
        try:
            attached_item = game_object.item_instance
        except ObjectDB.item_instance.RelatedObjectDoesNotExist:
            attached_item = None
        item = None
        if attached_item is not None:
            item = ItemInstance.objects.in_play().filter(
                pk=attached_item.pk, game_object=game_object, contained_in__isnull=True,
            ).first()
            if item is None:
                return None
    return ResolvedMenuTarget(
        request=request,
        label=_room_menu_label(room, game_object, actor, item),
        item=item,
        game_object=game_object,
    )


def _room_menu_label(
    room: ObjectDB,
    game_object: ObjectDB,
    viewer: ObjectDB,
    item: ItemInstance | None,
) -> str:
    """Read ordinary-object/exit presentation without initializing flow state.

    Args:
        room: The current real room, already checked by the resolver.
        game_object: The scoped ordinary Object or Exit, never a character.
        viewer: The actual actor whose observer-specific decorations apply.
        item: The validated attached item, if this is an item-backed Object.

    Returns:
        The consistent public item base or ordinary-object/exit base, projected
        through any existing flow-local presentation fields for this viewer.
    """
    # Room.scene_data is a cached property; reading its storage cannot invoke it.
    context = room.__dict__.get("scene_data")
    state = context.states.get(game_object.pk) if context is not None else None
    base = item.display_name if item is not None else game_object.key
    if state is None:
        return project_display_name(
            base, object_id=game_object.pk, viewer_id=viewer.pk,
        )
    if item is None:
        # Do not evaluate BaseState.name; explicit empty/null names are retained.
        base = state.__dict__.get("name", game_object.key)
    return project_display_name(
        base, object_id=game_object.pk, viewer_id=viewer.pk,
        fake_name=state.fake_name,
        real_name_viewers=state.real_name_viewers,
        name_prefix=state.name_prefix,
        name_suffix=state.name_suffix,
        name_prefix_map=state.name_prefix_map,
        name_suffix_map=state.name_suffix_map,
    )


def _resolve_menu_place(
    actor: ObjectDB,
    request: MenuTargetRequest,
) -> ResolvedMenuTarget | None:
    """Resolve an authored active place in the actor's current real room."""
    room = actor.location
    if room is None or not room.is_typeclass("typeclasses.rooms.Room", exact=False):
        return None
    profile = room.room_profile_or_none
    if profile is None:
        return None
    place = active_places(room_id=profile.pk).filter(pk=request.target_id).first()
    if place is None:
        return None
    return ResolvedMenuTarget(request=request, label=place.name, place=place)


def _resolve_contained_menu_item(
    actor: ObjectDB,
    request: MenuTargetRequest,
) -> ResolvedMenuTarget | None:
    """Resolve an immediate child under a current container assertion."""
    assert request.container_item_id is not None  # noqa: S101
    container_target = _resolve_menu_item(
        actor,
        MenuTargetRequest(MenuTargetKind.ITEMS, request.container_item_id),
    )
    if container_target is None:
        return None
    container = container_target.item
    if container is None or container.game_object is None:
        return None
    if not container.template.is_container:
        return None
    if container.template.supports_open_close and not container.is_open:
        return None
    item = (
        ItemInstance.objects.in_play()
        .filter(pk=request.target_id, contained_in=container)
        .select_related("template", "game_object")
        .first()
    )
    if item is None:
        return None
    game_object = item.game_object
    if game_object is not None:
        if game_object.location != container.game_object:
            return None
        if not passes_concealment_check(actor, game_object):
            return None
    return ResolvedMenuTarget(
        request=request,
        label=item.display_name,
        item=item,
        game_object=game_object,
    )
