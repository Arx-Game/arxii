"""Service functions for the overworld travel system (#1855).

The pathfinder (find_overworld_route) does BFS over TravelRoute edges
filtered by travel_mode, following the same frontier-batched pattern as
the room-level find_route() in world.areas.positioning.travel.
"""

from __future__ import annotations

from collections import deque
import math
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from world.travel.constants import VoyageStatus

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.ships.models import ShipDetails
    from world.travel.models import TravelHub, TravelMethod, TravelRoute, Voyage


def find_overworld_route(
    origin_hub: TravelHub,
    destination_hub: TravelHub,
    travel_mode: str,
) -> list[TravelRoute] | None:
    """BFS over TravelRoute edges filtered by travel_mode.

    Returns an ordered list of TravelRoute edges forming the route,
    or None if no route exists within OVERWORLD_MAX_HOPS. Follows the
    frontier-batched BFS pattern of find_route().
    """
    from world.travel.models import TravelRoute  # noqa: PLC0415

    if origin_hub.pk == destination_hub.pk:
        return []

    max_hops = settings.OVERWORLD_MAX_HOPS

    # Build adjacency from active routes matching travel_mode.
    # For bidirectional routes, both directions are usable.
    outbound = TravelRoute.objects.filter(
        travel_mode=travel_mode,
        is_active=True,
        origin_hub__is_active=True,
        destination_hub__is_active=True,
    )
    inbound = TravelRoute.objects.filter(
        travel_mode=travel_mode,
        is_active=True,
        is_bidirectional=True,
        origin_hub__is_active=True,
        destination_hub__is_active=True,
    )

    adjacency: dict[int, list[tuple[int, TravelRoute]]] = {}
    for route in outbound:
        adjacency.setdefault(route.origin_hub_id, []).append((route.destination_hub_id, route))
    for route in inbound:
        # Bidirectional: also allow travel from destination to origin
        adjacency.setdefault(route.destination_hub_id, []).append((route.origin_hub_id, route))

    visited: set[int] = {origin_hub.pk}
    # predecessor[hub_id] = (route_edge, previous_hub_id)
    predecessor: dict[int, tuple[TravelRoute, int]] = {}

    queue: deque[int] = deque([origin_hub.pk])

    for _hop in range(max_hops):
        if not queue:
            return None

        current = queue.popleft()
        for next_hub_id, route in adjacency.get(current, []):
            if next_hub_id in visited:
                continue
            visited.add(next_hub_id)
            predecessor[next_hub_id] = (route, current)

            if next_hub_id == destination_hub.pk:
                return _reconstruct_route(predecessor, origin_hub.pk, destination_hub.pk)

            queue.append(next_hub_id)

    return None


def _reconstruct_route(
    predecessor: dict[int, tuple[TravelRoute, int]],
    origin_id: int,
    destination_id: int,
) -> list[TravelRoute]:
    """Walk the predecessor chain backward from destination to origin, then reverse."""
    path: list[TravelRoute] = []
    current_id = destination_id
    while current_id != origin_id:
        route, prev_id = predecessor[current_id]
        path.append(route)
        current_id = prev_id
    path.reverse()
    return path


def compute_travel_time(
    route: TravelRoute,
    travel_method: TravelMethod,
    character_sheet: CharacterSheet,
    ship: ShipDetails | None = None,
) -> float:
    """Compute IC hours for one leg for a specific character.

    time = route.distance / effective_speed * route.difficulty_modifier
    where effective_speed = method.base_speed * ship_handling_factor (if ship)
    * (1 + travel_speed_modifier / 100)

    Per-character speed modifiers (weather, magic) are read via
    get_modifier_total(character_sheet, travel_speed_target). In the initial
    implementation, no source populates this modifier yet (the ModifierTarget
    is registered so the plumbing exists); the formula still accounts for it
    so future sources need no signature change.
    """
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415
    from world.mechanics.services import get_modifier_total  # noqa: PLC0415

    effective_speed = travel_method.base_speed

    if ship is not None and travel_method.ship_type is not None:
        handling_factor = ship.effective_handling() / travel_method.ship_type.base_handling
        effective_speed *= handling_factor

    # Per-character speed modifier (weather, magic) via the mechanics system.
    try:
        speed_target = ModifierTarget.objects.get(name="travel_speed", category__name="travel")
        speed_modifier = get_modifier_total(character_sheet, speed_target)
    except ModifierTarget.DoesNotExist:
        speed_modifier = 0

    effective_speed *= 1 + speed_modifier / 100

    if effective_speed <= 0:
        effective_speed = 0.01  # Prevent division by zero

    return route.distance / effective_speed * route.difficulty_modifier


def compute_ap_cost(ic_hours: float) -> int:
    """AP cost for a given IC travel time.

    ap_cost = ceil(ic_hours * AP_PER_IC_HOUR)
    """
    raw = ic_hours * settings.AP_PER_IC_HOUR
    return max(1, math.ceil(raw))


def compute_remaining_ap(
    voyage: Voyage,
    character_sheet: CharacterSheet,
    travel_method: TravelMethod,
    ship: ShipDetails | None = None,
) -> int:
    """Total AP to fast-forward from current hub to destination for this character.

    Sums compute_ap_cost(compute_travel_time(route, method, character_sheet, ship))
    for each remaining leg from current_leg_index to the end of route_hubs.
    Each participant may have a different remaining cost due to per-character
    speed modifiers.
    """
    total = 0
    hub_pks = voyage.route_hubs[voyage.current_leg_index + 1 :]

    prev_hub_id = voyage.route_hubs[voyage.current_leg_index]
    for hub_pk in hub_pks:
        route = _find_route_between(prev_hub_id, hub_pk, travel_method.travel_mode)
        if route is not None:
            total += compute_ap_cost(
                compute_travel_time(route, travel_method, character_sheet, ship)
            )
        prev_hub_id = hub_pk

    return total


def _find_route_between(
    origin_hub_id: int,
    destination_hub_id: int,
    travel_mode: str,
) -> TravelRoute | None:
    """Find a single TravelRoute edge between two adjacent hubs."""
    from world.travel.models import TravelRoute  # noqa: PLC0415

    route = TravelRoute.objects.filter(
        origin_hub_id=origin_hub_id,
        destination_hub_id=destination_hub_id,
        travel_mode=travel_mode,
        is_active=True,
    ).first()
    if route is not None:
        return route
    # Check reverse for bidirectional
    return TravelRoute.objects.filter(
        origin_hub_id=destination_hub_id,
        destination_hub_id=origin_hub_id,
        travel_mode=travel_mode,
        is_active=True,
        is_bidirectional=True,
    ).first()


# ---- Voyage lifecycle ----


class VoyageError(Exception):
    """Base exception for voyage operations."""

    def __init__(self, user_message: str = "Something went wrong with your voyage.") -> None:
        super().__init__(user_message)
        self.user_message = user_message

    """Base exception for voyage operations."""

    user_message: str = "Something went wrong with your voyage."


class NotVoyageLeaderError(VoyageError):
    def __init__(self, user_message: str = "Only the voyage leader can do that.") -> None:
        super().__init__(user_message)


class VoyageNotInTransitError(VoyageError):
    def __init__(self, user_message: str = "That voyage is no longer in progress.") -> None:
        super().__init__(user_message)


def _resolve_character_object(persona) -> object | None:
    """Resolve the ObjectDB character from a Persona.

    Persona → CharacterSheet → ObjectDB (the character the player is puppeting).
    """
    try:
        return persona.character_sheet.character
    except (AttributeError, ObjectDoesNotExist):
        return None


def _spend_ap(participant_persona, amount: int) -> bool:
    """Spend AP for a participant. Returns True if successful, False if can't afford."""
    from world.action_points.models import ActionPointPool  # noqa: PLC0415

    character_obj = _resolve_character_object(participant_persona)
    if character_obj is None:
        return False
    pool = ActionPointPool.get_or_create_for_character(character_obj)
    return pool.spend(amount)


def start_voyage(
    leader,
    destination_hub: TravelHub,
    travel_method: TravelMethod,
    ship: ShipDetails | None = None,
) -> Voyage:
    """Create a Voyage, compute route, enroll leader as participant.

    The leader is auto-enrolled as a VoyageParticipant — they pay AP
    for each leg like every other participant. The leader's current
    room must be a TravelHub whose travel_modes include the method's
    travel_mode (the embarkation constraint).
    """
    from world.travel.models import TravelHub, Voyage, VoyageParticipant  # noqa: PLC0415

    leader_obj = _resolve_character_object(leader)
    if leader_obj is None or leader_obj.location is None:
        raise VoyageError(user_message="You must be in a room to start a voyage.")

    try:
        origin_hub = TravelHub.objects.get(room_profile__objectdb=leader_obj.location)
    except TravelHub.DoesNotExist:
        raise VoyageError(user_message="You must be at a travel hub to start a voyage.") from None

    if not origin_hub.is_active:
        raise VoyageError(user_message="That hub is not active.")

    if travel_method.travel_mode not in (origin_hub.travel_modes or []):
        raise VoyageError(
            user_message=f"You can't start a {travel_method.travel_mode} voyage from here."
        )

    if not destination_hub.is_active:
        raise VoyageError(user_message="That destination hub is not active.")

    if travel_method.travel_mode not in (destination_hub.travel_modes or []):
        raise VoyageError(
            user_message=f"The destination doesn't support {travel_method.travel_mode} travel."
        )

    route = find_overworld_route(origin_hub, destination_hub, travel_method.travel_mode)
    if route is None:
        raise VoyageError(user_message="There's no route from here to that destination.")

    # Build the list of hub PKs: origin + all intermediate + destination
    hub_pks = [origin_hub.pk, *(edge.destination_hub_id for edge in route)]

    voyage = Voyage.objects.create(
        leader=leader,
        travel_method=travel_method,
        origin_hub=origin_hub,
        destination_hub=destination_hub,
        route_hubs=hub_pks,
        current_leg_index=0,
        status=VoyageStatus.IN_TRANSIT,
        ship=ship,
    )

    # Auto-enroll leader as participant
    VoyageParticipant.objects.create(voyage=voyage, persona=leader)

    return voyage


@transaction.atomic
def advance_leg(voyage: Voyage, caller) -> None:  # noqa: C901, PLR0912, PLR0915
    """Pay AP for next leg, move all participants to next hub room.

    Only the voyage leader may call this. Each participant's ActionPointPool.spend()
    is called individually. If any participant can't afford AP, they are left at
    the current hub (left_at set) and the rest of the group continues.

    If the caller can't afford their own AP, the entire advance fails atomically.

    If this advance moves the group to the final hub, the voyage auto-completes.
    """
    from world.travel.models import TravelHub, Voyage  # noqa: PLC0415

    voyage = (
        Voyage.objects.select_for_update()
        .select_related("travel_method", "destination_hub")
        .get(pk=voyage.pk)
    )

    if voyage.status != VoyageStatus.IN_TRANSIT:
        raise VoyageNotInTransitError

    if voyage.leader_id != caller.pk:
        raise NotVoyageLeaderError

    next_leg_index = voyage.current_leg_index + 1
    if next_leg_index >= len(voyage.route_hubs):
        raise VoyageError(user_message="You're already at your destination.")

    # Find the route edge for this leg
    current_hub_id = voyage.route_hubs[voyage.current_leg_index]
    next_hub_id = voyage.route_hubs[next_leg_index]
    route_edge = _find_route_between(current_hub_id, next_hub_id, voyage.travel_method.travel_mode)
    if route_edge is None:
        raise VoyageError(user_message="The route ahead seems to have vanished.")

    # Compute AP cost for each participant
    active_participants = list(
        voyage.participants.filter(left_at__isnull=True).select_related("persona")
    )

    # Check if caller is a participant
    caller_participant = next((p for p in active_participants if p.persona_id == caller.pk), None)
    if caller_participant is None:
        raise VoyageError(user_message="You're not part of this voyage.")

    # Compute costs for each participant
    costs: dict[int, int] = {}
    for participant in active_participants:
        try:
            character_sheet = participant.persona.character_sheet
        except (AttributeError, ObjectDoesNotExist):
            participant.left_at = timezone.now()
            participant.save()
            continue
        time = compute_travel_time(route_edge, voyage.travel_method, character_sheet, voyage.ship)
        costs[participant.pk] = compute_ap_cost(time)

    # Check caller can afford first — if not, fail atomically
    caller_cost = costs.get(caller_participant.pk, 0)
    if caller_cost > 0:
        if not _spend_ap(caller, caller_cost):
            raise VoyageError(user_message="You can't afford the AP for this leg.")

    # Now process other participants
    next_hub = TravelHub.objects.get(pk=next_hub_id)
    next_room = next_hub.room_profile.objectdb

    for participant in active_participants:
        if participant.persona_id == caller.pk:
            participant.legs_traveled += 1
            participant.save()
        else:
            ap = costs.get(participant.pk, 0)
            if ap > 0 and not _spend_ap(participant.persona, ap):
                participant.left_at = timezone.now()
                participant.save()
                continue
            participant.legs_traveled += 1
            participant.save()

        # Move character to next hub room
        char_obj = _resolve_character_object(participant.persona)
        if char_obj is not None and next_room is not None:
            from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415
            from flows.service_functions.movement import move_object  # noqa: PLC0415

            sdm = SceneDataManager()
            char_state = sdm.initialize_state_for_object(char_obj)
            room_state = sdm.initialize_state_for_object(next_room)
            move_object(char_state, room_state, quiet=False)

    voyage.current_leg_index = next_leg_index

    # Auto-complete if at final hub
    if next_leg_index >= len(voyage.route_hubs) - 1:
        voyage.status = VoyageStatus.ARRIVED
        voyage.completed_at = timezone.now()

    voyage.save()


@transaction.atomic
def complete_voyage(voyage: Voyage, caller) -> None:
    """Pay all remaining AP, move group directly to destination hub.

    Only the voyage leader may call this. Partial failure mirrors advance_leg:
    participants who can't afford are left behind; caller failing aborts atomically.
    """
    from world.travel.models import Voyage  # noqa: PLC0415

    voyage = Voyage.objects.select_for_update().get(pk=voyage.pk)

    if voyage.status != VoyageStatus.IN_TRANSIT:
        raise VoyageNotInTransitError

    if voyage.leader_id != caller.pk:
        raise NotVoyageLeaderError

    # If already at destination, just mark arrived
    if voyage.current_leg_index >= len(voyage.route_hubs) - 1:
        voyage.status = VoyageStatus.ARRIVED
        voyage.completed_at = timezone.now()
        voyage.save()
        return

    # Advance through all remaining legs
    while (
        voyage.status == VoyageStatus.IN_TRANSIT
        and voyage.current_leg_index < len(voyage.route_hubs) - 1
    ):
        advance_leg(voyage, caller)
        voyage.refresh_from_db()


def abandon_voyage(voyage: Voyage, caller) -> None:
    """End voyage at current hub. Participants stay where they are.

    If caller is leader: voyage status → ABANDONED, all participants notified.
    If caller is non-leader: only the caller is removed; voyage continues.
    """
    from world.travel.models import Voyage  # noqa: PLC0415

    voyage = Voyage.objects.select_for_update().get(pk=voyage.pk)

    if voyage.status != VoyageStatus.IN_TRANSIT:
        raise VoyageNotInTransitError

    caller_participant = voyage.participants.filter(
        persona_id=caller.pk, left_at__isnull=True
    ).first()

    if caller_participant is None:
        raise VoyageError(user_message="You're not part of this voyage.")

    if voyage.leader_id == caller.pk:
        voyage.status = VoyageStatus.ABANDONED
        voyage.completed_at = timezone.now()
        voyage.save()
        voyage.participants.filter(left_at__isnull=True).update(left_at=timezone.now())
    else:
        caller_participant.left_at = timezone.now()
        caller_participant.save()
