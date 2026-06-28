"""Flow CALL_SERVICE_FUNCTION handlers for the castable effect palette (#1584).

Each handler is keyword-only ``def h(*, payload) -> None`` and is referenced by
its dotted path from a seeded FlowDefinition's CALL_SERVICE_FUNCTION step.
"""

from typing import Any

from world.areas.positioning.models import Position
from world.areas.positioning.services import connect_positions, force_move_to_position


def move_position(*, payload: Any) -> None:
    """Relocate payload.target to payload.destination_position_id (force move).

    Uses force_move_to_position which bypasses capability and gate checks but
    requires destination to be in the same room as the objectdb.
    """
    dest = Position.objects.get(pk=payload.destination_position_id)
    force_move_to_position(payload.target, dest)


def create_obstacle(*, payload: Any) -> None:
    """Make the edge between two positions impassable (an obstacle).

    Connects payload.position_a_id and payload.position_b_id with is_passable=False.
    Passes blocks_flight from payload if present (defaults False).
    """
    a = Position.objects.get(pk=payload.position_a_id)
    b = Position.objects.get(pk=payload.position_b_id)
    blocks_flight = getattr(payload, "blocks_flight", False)  # noqa: GETATTR_LITERAL
    connect_positions(a, b, is_passable=False, blocks_flight=blocks_flight)
