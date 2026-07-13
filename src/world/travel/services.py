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
