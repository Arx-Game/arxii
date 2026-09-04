"""Shared opponent-line spawner for authored encounter rosters (#3425, #3565).

Two authoring surfaces share the same "creature x count x position hint"
shape: a Beat's ``BeatOpponentLine`` rows (session prep, ``RunBeatAction``)
and a scenario ``MissionOption``'s ``MissionOptionOpponentLine`` rows (a
scenario-graph ENCOUNTER option, ``world.missions.services.encounter_option``).
``spawn_opponent_lines`` is the one spawn loop both call - a bad line (a
deleted creature template, an unresolvable position) is logged and skipped
rather than aborting every other authored line.

Position resolution is inlined here rather than reused from
``commands.utils.gm_resolution.resolve_position_by_name``: ``world`` must
never import ``commands`` (the telnet-compatibility layer), so
``_resolve_position_by_name`` runs the same query that helper wraps
(case-insensitive exact match, falling back to a unique prefix match) but
returns ``None`` on no/ambiguous match instead of raising - the caller logs
and spawns without a position rather than refusing the whole line.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol

from django.db import transaction

if TYPE_CHECKING:
    from collections.abc import Iterable

    from evennia.accounts.models import AccountDB

    from world.areas.positioning.models import Position
    from world.combat.models import CombatEncounter, CreatureTemplate

logger = logging.getLogger(__name__)


class OpponentLineLike(Protocol):
    """Structural shape shared by ``BeatOpponentLine`` and ``MissionOptionOpponentLine``.

    Both are authored creature x count x position-hint rows, just keyed on a
    different parent (a Beat vs. a scenario MissionOption) - this protocol
    lets :func:`spawn_opponent_lines` stay agnostic to which one it's fed.
    """

    pk: int
    creature_template: CreatureTemplate
    count: int
    position_name: str
    order: int


def _resolve_position_by_name(room: object, name: str) -> Position | None:
    """Resolve a ``Position`` by name, scoped to *room*; ``None`` on no/ambiguous match.

    Mirrors ``commands.utils.gm_resolution.resolve_position_by_name``'s query
    (case-insensitive exact match, else a unique prefix match) - but ``world``
    must not import ``commands``, so the query is re-run here rather than
    reused, and a miss returns ``None`` (logged) instead of raising.
    """
    from world.areas.positioning.models import Position as PositionModel  # noqa: PLC0415

    positions = list(PositionModel.objects.filter(room=room))
    lname = name.lower()
    for position in positions:
        if position.name.lower() == lname:
            return position
    prefix_matches = [p for p in positions if p.name.lower().startswith(lname)]
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    if len(prefix_matches) > 1:
        logger.warning(
            "spawn_opponent_lines: '%s' is an ambiguous position name in room %s.", name, room
        )
        return None
    logger.warning("spawn_opponent_lines: no such position '%s' in room %s.", name, room)
    return None


def spawn_opponent_lines(
    encounter: CombatEncounter,
    lines: Iterable[OpponentLineLike],
    *,
    acting_account: AccountDB | None = None,
) -> list[dict[str, Any]]:
    """Spawn every authored opponent line onto ``encounter``; per-line log-and-continue.

    Returns the per-line outcome dicts (``line_id``, ``creature``,
    ``opponent_id``/``success``/``message``) callers surface in their own
    result payloads. A line whose spawn fails (e.g. the encounter's scaling
    formula rejecting the template) is logged and skipped rather than
    aborting the whole roster - the mission-grant log-and-continue pattern.
    """
    from world.areas.positioning.exceptions import PositionError  # noqa: PLC0415
    from world.combat.services import spawn_from_creature_template  # noqa: PLC0415

    room = encounter.room
    outcomes: list[dict[str, Any]] = []
    for line in lines:
        position = None
        note = ""
        if line.position_name and room is not None:
            position = _resolve_position_by_name(room, line.position_name)
            if position is None:
                note = f"position '{line.position_name}' not found; spawned without it"
        for _index in range(line.count):
            try:
                with transaction.atomic():
                    opponent = spawn_from_creature_template(
                        encounter,
                        line.creature_template,
                        position=position,
                        acting_account=acting_account,
                    )
            except (ValueError, PositionError) as exc:
                logger.warning(
                    "spawn_opponent_lines: failed to spawn opponent line %s (encounter %s): %s",
                    line.pk,
                    encounter.pk,
                    exc,
                )
                outcomes.append(
                    {
                        "line_id": line.pk,
                        "creature": line.creature_template.name,
                        "success": False,
                        "message": str(exc),
                    }
                )
                continue
            outcomes.append(
                {
                    "line_id": line.pk,
                    "creature": line.creature_template.name,
                    "opponent_id": opponent.pk,
                    "success": True,
                    "message": note,
                }
            )
    return outcomes
