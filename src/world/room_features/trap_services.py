"""Trap resolution services (#1051, #520 Phase 6, #1317).

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

A trap may optionally be anchored to a specific ``Position`` (#1317) rather than
covering the whole room — used for hazards a knockback can land a target on/into.
Room-wide traps (``position=None``) behave exactly as before this addition;
position-scoped traps additionally require the entrant to actually occupy that
Position, whether they walked there (``check_room_traps_on_entry``, which derives
the entrant's landing Position) or were knocked there
(``check_traps_at_position``, called with the already-known landing Position).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from world.checks.consequence_resolution import (
    apply_pool_deterministically,
    apply_resolution,
    resolve_pool_consequences,
    select_consequence,
)
from world.checks.types import ResolutionContext

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models.consequence_pools import ConsequencePool
    from typeclasses.characters import Character
    from world.areas.positioning.models import Position
    from world.checks.models import CheckType
    from world.checks.types import PendingResolution
    from world.room_features.models import Trap


def check_room_traps_on_entry(character: Character, room: ObjectDB) -> None:
    """Resolve every armed, not-yet-resolved trap relevant to ``character``'s
    entry into ``room``.

    Best-effort entry point for the movement hook: a target with no
    ``room_profile`` (e.g. not a real room) or no sheet, and a room with no
    armed traps, are all no-ops. Derives the entrant's landing Position (if
    any) so position-scoped traps anchored there are included alongside
    room-wide ones.
    """
    from world.areas.positioning.services import position_of  # noqa: PLC0415

    try:
        profile = room.room_profile
    except (AttributeError, ObjectDoesNotExist):
        return
    try:
        sheet = character.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return

    landing_position = position_of(character)
    _resolve_relevant_traps(character, profile, sheet, landing_position)


def check_traps_at_position(character: Character, position: Position) -> None:
    """Resolve every armed, not-yet-resolved trap relevant to ``character``
    occupying ``position`` — room-wide traps plus any trap anchored to this
    exact Position.

    Called after a forced position change (e.g. a knockback, #1317) that
    doesn't route through the room-entry movement hook. Best-effort: a
    position whose room has no ``room_profile``, or a character with no
    sheet, are no-ops (same tolerance as ``check_room_traps_on_entry``).
    """
    try:
        profile = position.room.room_profile
    except (AttributeError, ObjectDoesNotExist):
        return
    try:
        sheet = character.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return

    _resolve_relevant_traps(character, profile, sheet, position)


def _resolve_relevant_traps(character, profile, sheet, position) -> None:
    """Shared filter: room-wide traps (position=None) plus the trap anchored
    to ``position`` (if any), excluding traps already resolved for ``sheet``.
    """
    query = Q(position__isnull=True)
    if position is not None:
        query |= Q(position=position)
    armed_traps = list(profile.traps.filter(query, is_armed=True).exclude(detected_by=sheet))
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


def fire_pool_at_characters(
    pool: ConsequencePool,
    characters: Iterable[ObjectDB],
    *,
    source_character: ObjectDB | None = None,
) -> None:
    """Fire *pool* deterministically (no roll) against every character in *characters*.

    Unlike ``_resolve_trap_pool`` (rolls a detection check, then applies ONE
    selected consequence), this fires every authored consequence in the pool
    unconditionally — extracted so callers who already know the pool must go
    off (no detection roll makes sense) reuse the same
    ``apply_pool_deterministically`` plumbing rather than duplicating it.
    Used by redirect-detonation resolution (#2210) to fire a volatile object's
    ``PropertyDetonation.consequence_pool`` at every combatant positioned there.

    Typed ``ObjectDB`` (not the narrower ``Character``) to match
    ``ResolutionContext.character``'s own typing — callers pass whichever
    ObjectDB-typed actors/targets they already have on hand (participants'
    characters, opponents' objectdbs); this module isn't in the
    ``objectdb-param`` lint's current scope.
    """
    for character in characters:
        context = ResolutionContext(character=source_character or character, target=character)
        apply_pool_deterministically(pool=pool, context=context)


# ---------------------------------------------------------------------------
# Zone hazard lifecycle (#2019)
# ---------------------------------------------------------------------------


def tick_zone_hazards(room: ObjectDB) -> None:
    """Decrement duration on all armed zone hazards in the room.

    Zone hazards are Traps with ``duration_rounds`` not null. At 0, the hazard
    is disarmed (``is_armed=False``). Does NOT deal damage — damage is handled
    by the combat/scene round-tick applying the consequence_pool to occupants.

    Staff-authored traps (null ``duration_rounds``) are never decremented.
    """
    from world.room_features.models import Trap  # noqa: PLC0415

    hazards = Trap.objects.filter(
        is_armed=True,
        duration_rounds__isnull=False,
        room_profile__objectdb=room,
    )
    for hazard in hazards:
        hazard.duration_rounds -= 1
        if hazard.duration_rounds <= 0:
            hazard.is_armed = False
        hazard.save(update_fields=["duration_rounds", "is_armed"])


def teardown_conjured_hazards(room: ObjectDB) -> None:
    """Disarm all conjured hazards (created_by_sheet not null) in a room.

    Called at encounter-end / scene-end to prevent permanent hazards.
    Staff-authored traps (null ``created_by_sheet``) are never touched.
    """
    from world.room_features.models import Trap  # noqa: PLC0415

    Trap.objects.filter(
        created_by_sheet__isnull=False,
        room_profile__objectdb=room,
    ).update(is_armed=False)
