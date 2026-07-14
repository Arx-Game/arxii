"""Servant fetch service (#2276).

Intercepts the ``NotReachable`` path for item/outfit retrieval when an
active SERVANT ``NPCAssignment`` exists in the actor's estate. The servant
queues a delayed fetch with room echoes: a departure echo, a delay, then
the item appears and an arrival echo fires.

The interception happens at the **action layer** (``GetAction``,
``TakeOutAction``, ``ApplyOutfitAction``), not the service layer — the
service functions (``pick_up``, ``take_out``, ``apply_outfit``) raise
``NotReachable`` unchanged. Only the action's ``execute()`` catches it
and delegates here.

Cancellation mirrors ``TravelAction``: a ``.ndb.active_fetch_token``
makes stale callbacks no-op when the actor moves before the delay fires.
``cancel_servant_fetch`` is called from ``Character.at_post_move``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import uuid

from django.db import transaction
from evennia.utils import delay

from world.areas.services import get_room_profile
from world.npc_services.models import AssignmentRole, NPCAssignment

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.items.models import ItemInstance, Outfit


#: Default delay (seconds) before a servant fetch completes.
DEFAULT_FETCH_DELAY_SECONDS: float = 5.0


def find_servant(room: ObjectDB) -> NPCAssignment | None:
    """Return the active SERVANT NPCAssignment in the room's area-closure chain, or None.

    Walks the same ``AreaClosure`` chain as ``is_owner``/``is_tenant``.
    Queries ``NPCAssignment`` for SERVANT role across all rooms whose
    ``RoomProfile.area`` is an ancestor of (or equal to) the actor's room's
    area. One servant per estate is the expected common case; if multiple
    exist, the most recently assigned wins (``ordering = ["-assigned_at"]``).
    """
    from world.areas.models import AreaClosure  # noqa: PLC0415

    profile = get_room_profile(room)
    if profile is None or profile.area is None:
        return None

    ancestor_ids = list(
        AreaClosure.objects.filter(descendant_id=profile.area.pk).values_list(
            "ancestor_id", flat=True
        )
    )
    if not ancestor_ids:
        return None

    return (
        NPCAssignment.objects.filter(
            room__area_id__in=ancestor_ids,
            assignment_role=AssignmentRole.SERVANT,
            is_active=True,
        )
        .select_related("functionary", "npc_asset")
        .first()
    )


def can_servant_fetch(*, actor: ObjectDB, item_instance: ItemInstance) -> bool:  # noqa: PLR0911
    """Eligibility check: may a servant fetch this item for this actor?

    Returns True only when ALL of:
        1. The actor has an active persona with owner or tenant standing
           at their current location (``is_owner`` or ``is_tenant``).
        2. An active SERVANT ``NPCAssignment`` exists in the estate
           (area-closure chain of the actor's room).
        3. The item has a ``game_object``.
        4. The item's topmost container's location is in a DIFFERENT room
           than the actor — a closed container in the same room does not
           qualify (the servant cannot open containers).

    Does NOT raise — returns False if any step fails.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.locations.services import is_owner, is_tenant  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    # Resolve the actor's active persona.
    try:
        sheet = actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return False
    persona = active_persona_for_sheet(sheet)
    if persona is None:
        return False

    # Check owner/tenant standing.
    if actor.location is None:
        return False
    if not (is_owner(persona, actor.location) or is_tenant(persona, actor.location)):
        return False

    # Check servant exists in the estate.
    if find_servant(actor.location) is None:
        return False

    # Check the item has a game_object.
    if item_instance.game_object is None:
        return False

    # Walk contained_in to the topmost item.
    topmost = item_instance
    while topmost.contained_in is not None:
        topmost = topmost.contained_in

    # The item must be in a DIFFERENT room (not a same-room closed container).
    if topmost.game_object is None:
        return False
    if topmost.game_object.location == actor.location:
        return False

    return True


def servant_fetch_item(
    *,
    actor: ObjectDB,
    item_instance: ItemInstance,
    delay_seconds: float = DEFAULT_FETCH_DELAY_SECONDS,
) -> bool:
    """Queue a delayed item fetch with room echoes.

    Emits a departure echo to the actor's room, schedules a delayed
    callback via ``evennia.utils.delay()``, and stores the cancellation
    token on ``actor.ndb``. The callback is ``@transaction.atomic`` and:

    1. Checks the token (stale → no-op, actor moved).
    2. Moves the item's ``game_object`` to the actor (into inventory).
    3. Clears ``contained_in`` if set.
    4. Sets ``holder_character_sheet`` if the item was unowned.
    5. Invalidates the actor's ``carried_items`` cache.
    6. Emits an arrival echo.

    Args:
        actor: The character requesting the fetch.
        item_instance: The item to fetch.
        delay_seconds: Seconds before the fetch completes.

    Returns:
        True if the fetch was queued.
    """
    from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415
    from flows.service_functions.communication import (  # noqa: PLC0415
        message_location,
    )

    servant = find_servant(actor.location)
    servant_name = servant.get_active_target_name() if servant else "A servant"

    # Departure echo.
    sdm = SceneDataManager()
    actor_state = sdm.initialize_state_for_object(actor)
    item_name = item_instance.display_name
    message_location(
        actor_state,
        f"{servant_name} bows and departs to fetch {item_name}.",
    )

    # Cancellation token.
    token = uuid.uuid4()
    actor.ndb.active_fetch_token = token
    task = delay(
        delay_seconds,
        _complete_item_fetch,
        actor,
        item_instance,
        token,
        servant_name,
    )
    actor.ndb.active_fetch_task = task
    return True


@transaction.atomic
def _complete_item_fetch(
    actor: ObjectDB,
    item_instance: ItemInstance,
    token: uuid.UUID,
    servant_name: str,
) -> None:
    """Delayed completion: move the item to the actor and emit arrival echo.

    Wrapped in ``@transaction.atomic`` so partial failures (move succeeds
    but holder save fails) roll back — mirroring the ``pick_up`` / ``take_out``
    service functions' own atomicity.
    """
    # Stale callback — actor moved or a new fetch superseded this one.
    current_token = actor.ndb.active_fetch_token
    if current_token != token:
        return

    if item_instance.game_object is None:
        return

    # Clear container nesting if any.
    if item_instance.contained_in is not None:
        item_instance.contained_in = None
        item_instance.save(update_fields=["contained_in"])

    # Move to the actor (into inventory, not just the room).
    if not item_instance.game_object.move_to(actor, quiet=True):
        return

    # Set holder if unowned (same logic as pick_up).
    taker_sheet = actor.character_sheet
    if item_instance.holder_character_sheet_id is None and taker_sheet is not None:
        item_instance.holder_character_sheet = taker_sheet
        item_instance.save(update_fields=["holder_character_sheet"])

    # Invalidate carried-items cache.
    if hasattr(actor, "carried_items"):
        actor.carried_items.invalidate()

    # Arrival echo.
    from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415
    from flows.service_functions.communication import (  # noqa: PLC0415
        message_location,
    )

    sdm = SceneDataManager()
    actor_state = sdm.initialize_state_for_object(actor)
    item_name = item_instance.display_name
    message_location(
        actor_state,
        f"{servant_name} returns with {item_name} and hands it to $You().",
    )

    # Clear token.
    actor.ndb.active_fetch_token = None
    actor.ndb.active_fetch_task = None


def servant_fetch_outfit(
    *,
    actor: ObjectDB,
    outfit: Outfit,
    delay_seconds: float = DEFAULT_FETCH_DELAY_SECONDS,
) -> bool:
    """Queue a delayed outfit fetch with room echoes.

    The servant brings individual outfit pieces to the actor and equips
    them via the existing ``equip()`` service. The wardrobe stays in place
    — narratively correct (a servant brings clothes, not the armoire).

    The completion callback is ``@transaction.atomic`` and:
    1. Checks the token (stale → no-op).
    2. For each outfit slot: moves the piece's ``game_object`` to the
       actor (NOT to the room — ``equip()``'s ``can_equip`` checks
       ``is_in_possession``, which requires ``game_object.location == actor``).
       Clears ``contained_in``, then calls ``equip()``.
    3. Emits an arrival echo.
    4. Clears the token.

    Args:
        actor: The character requesting the outfit.
        outfit: The ``Outfit`` to fetch and equip.
        delay_seconds: Seconds before the fetch completes.

    Returns:
        True if the fetch was queued.
    """
    from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415
    from flows.service_functions.communication import (  # noqa: PLC0415
        message_location,
    )

    servant = find_servant(actor.location)
    servant_name = servant.get_active_target_name() if servant else "A servant"

    # Departure echo.
    sdm = SceneDataManager()
    actor_state = sdm.initialize_state_for_object(actor)
    message_location(
        actor_state,
        f"{servant_name} bows and departs to fetch your {outfit.name}.",
    )

    # Cancellation token.
    token = uuid.uuid4()
    actor.ndb.active_fetch_token = token
    task = delay(
        delay_seconds,
        _complete_outfit_fetch,
        actor,
        outfit,
        token,
        servant_name,
    )
    actor.ndb.active_fetch_task = task
    return True


@transaction.atomic
def _complete_outfit_fetch(
    actor: ObjectDB,
    outfit: Outfit,
    token: uuid.UUID,
    servant_name: str,
) -> None:
    """Delayed completion: bring outfit pieces and equip them.

    Wrapped in ``@transaction.atomic`` so partial failures roll back.
    """
    # Stale callback.
    current_token = actor.ndb.active_fetch_token
    if current_token != token:
        return

    from flows.object_states.item_state import ItemState  # noqa: PLC0415
    from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415
    from flows.service_functions.communication import (  # noqa: PLC0415
        message_location,
    )
    from flows.service_functions.inventory import equip  # noqa: PLC0415
    from world.items.exceptions import InventoryError  # noqa: PLC0415

    sdm = SceneDataManager()
    actor_state = sdm.initialize_state_for_object(actor)

    for slot in outfit.slots.all():
        piece = slot.item_instance
        if piece.game_object is None:
            continue
        # Clear container nesting.
        if piece.contained_in is not None:
            piece.contained_in = None
            piece.save(update_fields=["contained_in"])
        # Move to the actor (NOT the room — equip() requires possession).
        if not piece.game_object.move_to(actor, quiet=True):
            continue
        # Equip the piece.
        item_state = ItemState(piece, context=sdm)
        try:
            equip(actor_state, item_state)
        except InventoryError:
            # If a piece can't be equipped (slot conflict, etc.), skip it.
            # The transaction will still commit the moves that succeeded.
            continue

    # Arrival echo.
    message_location(
        actor_state,
        f"{servant_name} returns with your {outfit.name} and helps you change.",
    )

    # Clear token.
    actor.ndb.active_fetch_token = None
    actor.ndb.active_fetch_task = None


def cancel_servant_fetch(actor: ObjectDB) -> None:
    """Cancel an in-progress servant fetch, if any.

    Called from ``Character.at_post_move`` when the actor leaves the room.
    Cancels the pending delay task and clears the token so the stale
    callback no-ops.
    """
    token = actor.ndb.active_fetch_token
    if token is None:
        return
    task = actor.ndb.active_fetch_task
    if task is not None:
        task.cancel()
    actor.ndb.active_fetch_token = None
    actor.ndb.active_fetch_task = None
