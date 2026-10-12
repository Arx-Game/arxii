"""Resolving a cast's position parameters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.errors import ActionDispatchError
from world.combat.models import CombatParticipant

if TYPE_CHECKING:
    from world.areas.positioning.models import Position
    from world.magic.models import Technique


def resolve_cast_position_params(
    participant: CombatParticipant,
    technique: Technique,
    position_params: dict[str, int],
) -> dict[str, Position | None]:
    """Validate declared cast positions against the encounter's room + technique reach.

    ``position_params`` is the raw dispatch payload — either a single
    ``destination_position_id`` (single-position techniques such as Phase Jump /
    Force Grip / zone hazards) or a ``position_a_id``/``position_b_id`` pair
    (Barricade-style two-endpoint techniques). Both shapes are optional and
    mutually independent; an empty/absent ``position_params`` resolves to all-None.

    Raises ``ActionDispatchError`` (mirroring the existing ally-target /
    positional-reach error path used elsewhere in this module):

    - ``UNKNOWN_ACTION_REF`` — a supplied position id does not resolve to a
      ``Position`` in the encounter's own room, the a/b pair is only
      half-supplied, or the a/b pair is identical (a barrier needs two
      different endpoints).
    - ``TARGET_OUT_OF_REACH`` — the declared destination is beyond
      ``technique.reach`` from the caster's current position. Skipped when the
      caster is unplaced (no current_position) — lenient, same rationale as
      ``_validate_technique_reach``.
    """
    from world.areas.positioning.models import Position  # noqa: PLC0415
    from world.areas.positioning.services import position_reachable  # noqa: PLC0415

    room = participant.encounter.room
    resolved: dict[str, Position | None] = {
        "cast_destination": None,
        "cast_position_a": None,
        "cast_position_b": None,
    }

    def _get(pk: int) -> Position:
        pos = Position.objects.filter(pk=pk, room=room).first()
        if pos is None:
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)
        return pos

    dest_id = position_params.get("destination_position_id")
    if dest_id:
        dest = _get(dest_id)
        origin = participant.current_position
        if origin is not None and not position_reachable(
            origin, dest, technique.reach, reach_hops=technique.reach_hops
        ):
            raise ActionDispatchError(ActionDispatchError.TARGET_OUT_OF_REACH)
        resolved["cast_destination"] = dest

    a_id = position_params.get("position_a_id")
    b_id = position_params.get("position_b_id")
    if bool(a_id) != bool(b_id):
        raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)
    if a_id and b_id:
        if a_id == b_id:
            # A barrier needs two different endpoints — reject a degenerate pair
            # before it ever reaches the resolver.
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)
        resolved["cast_position_a"] = _get(a_id)
        resolved["cast_position_b"] = _get(b_id)

    return resolved
