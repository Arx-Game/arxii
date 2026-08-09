"""Trap resolution services (#1051, #520 Phase 6, #1317, #3011).

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

``search_room_traps`` (#3011) is the deliberate-search sibling of entry
resolution: a player who stops and searches rolls each armed, hidden,
not-yet-detected trap's own ``detect_check_type`` with no consequence on
failure (only physically entering can trigger one). ``is_hidden=False`` gives
both entry and search paths their first reader — a not-hidden trap needs no
roll anywhere; it is already visible via the room trap list
(``world.room_features.views_traps.RoomTrapViewSet``).
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
    from evennia_extensions.models import RoomProfile
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

    ``is_hidden=False`` (#3011) skips the roll entirely: a not-hidden armed
    trap is authored as an obvious hazard, already visible to everyone in the
    room's trap list (``world.room_features.views_traps.RoomTrapViewSet``), so
    entering the room is always a clean avoidance -- no roll, no consequence.
    A hidden trap rolls as before, and messages the character directly
    (detector-only) with what happened, since entry is the one detection path
    with no ``ActionResult`` of its own to carry the news.
    """
    sheet = character.sheet_data
    if not trap.is_hidden:
        trap.detected_by.add(sheet)
        return
    pending = _resolve_trap_pool(trap, character, trap.detect_check_type, trap.detect_difficulty)
    trap.detected_by.add(sheet)
    # A real (saved) selected_consequence means the rolled outcome tier matched
    # an authored pool entry and effects were applied (`apply_resolution` ->
    # `apply_all_effects` no-ops on an unsaved/fallback consequence, pk=None) --
    # the same signal ``_resolve_trap_pool`` -> ``apply_resolution`` already
    # acted on, not a fresh success_level sign check (a pool's "avoided" tier
    # need not be the outcome catalog's most-positive one).
    triggered = pending.selected_consequence.pk is not None
    if triggered:
        character.msg(f"You trigger {trap.name}!")
    else:
        character.msg(f"You spot {trap.name} and step carefully around it.")


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


def search_room_traps(character: Character, room_profile: RoomProfile) -> list[Trap]:
    """Roll every armed, hidden, not-yet-detected trap's own ``detect_check_type``
    against a deliberate search (#3011).

    Sibling of ``world.clues.services.search_room`` rather than folded into it: a
    trap's check type and difficulty are authored per-trap (unlike the single
    shared Search ``CheckType`` clues roll against), and keeping the query on this
    side of the room_features/clues boundary means clues never needs to import a
    Trap. Called by ``SearchAction`` alongside ``search_room``, not by
    ``search_room`` itself.

    Not-hidden traps are skipped here -- ``is_hidden=False`` already makes them
    visible with no roll (see ``resolve_trap_on_character``), and re-rolling them
    on a search would be redundant. A failed roll here does nothing (the trap
    stays hidden, no consequence fires) -- unlike physically walking into one, a
    search that comes up empty is just missing it, not triggering it.

    Returns the traps newly detected by this search, for the caller's message.
    """
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.room_features.models import Trap  # noqa: PLC0415

    try:
        sheet = character.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return []

    candidates = Trap.objects.filter(
        room_profile=room_profile, is_armed=True, is_hidden=True
    ).exclude(detected_by=sheet)

    detected: list[Trap] = []
    for trap in candidates:
        result = perform_check_with_modifiers(
            character, trap.detect_check_type, target_difficulty=trap.detect_difficulty
        )
        if result.outcome is not None and result.outcome.success_level >= 0:
            trap.detected_by.add(sheet)
            detected.append(trap)
    return detected


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

    conjured = Trap.objects.filter(
        created_by_sheet__isnull=False,
        room_profile__objectdb=room,
    )
    # Per-instance save, not a bulk update: Trap is a SharedMemoryModel, and a
    # bulk .update() sends no post_save signal, so the idmapper identity map
    # keeps serving a stale is_armed=True to anything already holding that
    # Trap (e.g. a GM's own trap listing right after this teardown runs).
    for hazard in conjured:
        hazard.is_armed = False
        hazard.save(update_fields=["is_armed"])
