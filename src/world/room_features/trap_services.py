"""Trap resolution services (#1051, #520 Phase 6).

Entry resolution is called directly from the movement hook
(``Character.at_post_move``) — mirroring mission ROOM_TRIGGER dispatch (#729) —
because the reactive Trigger-row system is anchored to ConditionInstances and
does not fit a room-bound entity. A cheap ``profile.traps`` query short-circuits
for ordinary rooms.

A trap's graded damage lives entirely in its ``consequence_pool``: the detection
roll's outcome tier selects the consequence to apply, so a success tier (no
consequence authored) means the entrant spotted and avoided the trap, while a
failure tier fires the authored damage through the standard effect-handler path
(``apply_resolution`` -> ``_deal_damage`` -> ``process_damage_consequences``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.checks.consequence_resolution import (
    apply_resolution,
    resolve_pool_consequences,
    select_consequence,
)
from world.checks.types import ResolutionContext

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from typeclasses.characters import Character
    from world.checks.models import CheckType
    from world.checks.types import PendingResolution
    from world.room_features.models import Trap


def check_room_traps_on_entry(character: Character, room: ObjectDB) -> None:
    """Resolve every armed, not-yet-resolved trap in ``room`` against ``character``.

    Best-effort entry point for the movement hook: a target with no
    ``room_profile`` (e.g. not a real room) or no sheet, and a room with no
    armed traps, are all no-ops.
    """
    try:
        profile = room.room_profile
    except (AttributeError, ObjectDoesNotExist):
        return
    try:
        sheet = character.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return

    armed_traps = list(profile.traps.filter(is_armed=True).exclude(detected_by=sheet))
    for trap in armed_traps:
        resolve_trap_on_character(trap, character)


def resolve_trap_on_character(trap: Trap, character: Character) -> None:
    """Roll ``trap``'s detection check and apply the graded pool outcome.

    Marks the trap resolved for this character afterward so it neither
    re-triggers nor stays hidden for them on re-entry.
    """
    _resolve_trap_pool(trap, character, trap.detect_check_type, trap.detect_difficulty)
    trap.detected_by.add(character.sheet_data)


def _resolve_trap_pool(
    trap: Trap,
    character: Character,
    check_type: CheckType,
    difficulty: int,
) -> PendingResolution:
    """Roll ``check_type`` and apply the selected consequence from the pool.

    Returns the ``PendingResolution`` so callers (disarm) can branch on the
    outcome tier without rolling twice.
    """
    consequences = resolve_pool_consequences(trap.consequence_pool)
    pending = select_consequence(character, check_type, difficulty, consequences)
    context = ResolutionContext(character=character, target=character)
    apply_resolution(pending, context)
    return pending
