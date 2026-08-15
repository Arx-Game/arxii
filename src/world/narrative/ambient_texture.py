"""Periodic ambient room texture: roaming flavor + room-state risk telegraphing (#2988).

Sibling of ``weather.tasks`` and ``weather.services`` in shape: ``select_ambient_emit`` is
the selection seam (mirrors ``select_weather_emit``); ``roll_and_echo_ambient_texture`` is the
driver, registered with the ``game_clock`` scheduler exactly like ``roll_and_echo_weather``
(checked every tick, no-ops unless the IC time-of-day phase transitioned since the last run,
shared guard: ``game_clock.task_registry.phase_transitioned_since_last_run``).

One model (``AmbientEmit``) serves both plain roaming flavor and risk telegraphing — the only
difference is whether a row carries a ``gate_stat_key``. This module is text-only delivery: no
NPC/encounter spawning (that's #2378's job, off this same ``world.locations`` substrate).

**Delivery audience is derived from online sessions, never a grid-wide room scan** (#2988
Decision 5): the candidate room set is exactly the distinct rooms currently-connected
sessions' puppets occupy, so per-tick cost is bounded by online-player count, not map size.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

from flows.service_functions.perception_registry import resolve_broadcast_exclusions
from world.checks.outcome_utils import select_weighted
from world.game_clock.services import get_ic_phase, get_ic_season
from world.game_clock.task_registry import phase_transitioned_since_last_run
from world.locations.services import effective_values_for_rooms
from world.narrative.constants import NarrativeCategory
from world.narrative.models import AmbientEmit
from world.narrative.services import send_narrative_message

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

    from evennia_extensions.models import RoomProfile
    from world.character_sheets.models import CharacterSheet
    from world.game_clock.constants import Season, TimePhase
    from world.locations.constants import StatKey

AMBIENT_TASK_KEY = "narrative.ambient_roll"


def _room_scope(room: DefaultObject) -> tuple[RoomProfile | None, list[int]]:
    """A room's RoomProfile plus its area ancestor ids (closure, including itself at depth 0).

    Narrow re-derivation of ``world.locations.services._room_profile_and_ancestors``'s shape
    — that helper is module-private to ``locations``, so this stays a small,
    ``narrative``-owned query rather than a cross-app private import.
    """
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.areas.models import AreaClosure  # noqa: PLC0415

    try:
        profile = room.room_profile
    except RoomProfile.DoesNotExist:
        return None, []
    area = profile.area
    if area is None:
        return profile, []
    ancestor_ids = list(
        AreaClosure.objects.filter(descendant_id=area.pk).values_list("ancestor_id", flat=True)
    )
    return profile, ancestor_ids


def _scope_pool(room: DefaultObject) -> list[AmbientEmit]:
    """The most-specific non-empty scope pool for a room: room > area > generic (Decision 2).

    Existence, not eligibility, decides the pool — mirrors the location cascade's
    override-wins convention (a scope's presence shadows a broader one regardless of whether
    any of its own rows happen to be season/phase/gate-eligible this tick).
    """
    profile, ancestor_ids = _room_scope(room)

    if profile is not None:
        room_rows = list(AmbientEmit.objects.filter(room_profile=profile))
        if room_rows:
            return room_rows

    if ancestor_ids:
        area_rows = list(
            AmbientEmit.objects.filter(area_id__in=ancestor_ids).select_related("area")
        )
        if area_rows:
            best_level = min(row.area.level for row in area_rows)
            return [row for row in area_rows if row.area.level == best_level]

    return list(AmbientEmit.objects.filter(area__isnull=True, room_profile__isnull=True))


def _cooldown_clear(row: AmbientEmit, now: datetime) -> bool:
    if row.last_fired_at is None:
        return True
    return now >= row.last_fired_at + timedelta(minutes=row.cooldown_minutes)


def _gate_values(room: DefaultObject, stat_keys: set[StatKey]) -> dict[StatKey, int]:
    """Bulk-resolve every distinct gated stat axis a candidate pool needs, in one query batch.

    One ``effective_values_for_rooms`` call for every candidate row's ``gate_stat_key``,
    instead of a separate ``effective_value`` cascade walk per row (the same room's cascade
    would otherwise be re-walked once per gated candidate).
    """
    if not stat_keys:
        return {}
    values = effective_values_for_rooms([room], stat_keys=stat_keys)
    return values.get(room.pk, {})  # type: ignore[return-value]


def _gate_clear(row: AmbientEmit, gate_values: dict[StatKey, int]) -> bool:
    """Whether a row's single-axis room-state gate (Decision 3) admits this room right now."""
    if not row.gate_stat_key:
        return True
    value = gate_values.get(row.gate_stat_key, 0)
    if row.gate_min is not None and value < row.gate_min:
        return False
    return not (row.gate_max is not None and value > row.gate_max)


def select_ambient_emit(
    room: DefaultObject,
    *,
    season: Season | None = None,
    phase: TimePhase | None = None,
    now: datetime | None = None,
) -> AmbientEmit | None:
    """Pick a weighted-random ``AmbientEmit`` for a room right now, or None.

    Resolves the room's most-specific non-empty scope pool (room > area > generic, Decision
    2), filters to rows flagged for the current IC season *and* phase (like
    ``select_weather_emit``), excludes rows still in cooldown, excludes rows whose
    ``gate_stat_key`` doesn't clear against the room's cascade-resolved value (Decision 3 —
    this is the whole "risk telegraph" mechanism, no second model), then weighted-random picks
    among what's left. Returns None on no IC clock or no eligible row — best-effort, quiet.
    """
    if season is None:
        season = get_ic_season()
    if phase is None:
        phase = get_ic_phase()
    if season is None or phase is None:
        return None
    if now is None:
        now = timezone.now()

    candidates = _scope_pool(room)
    if not candidates:
        return None

    eligible = [
        row
        for row in candidates
        if getattr(row, f"in_{season.value}") and getattr(row, f"at_{phase.value}")
    ]
    eligible = [row for row in eligible if _cooldown_clear(row, now)]
    gate_keys = {row.gate_stat_key for row in eligible if row.gate_stat_key}
    gate_values = _gate_values(room, gate_keys)
    eligible = [row for row in eligible if _gate_clear(row, gate_values)]
    if not eligible:
        return None
    return select_weighted(eligible)


def _online_occupied_rooms() -> tuple[dict[int, DefaultObject], dict[int, list[CharacterSheet]]]:
    """Distinct rooms holding an online occupant, plus each room's online CharacterSheets.

    Derived from live sessions (``evennia.SESSION_HANDLER``), never a grid-wide room scan
    (Decision 5) — per-tick cost is bounded by online-player count, not map size.

    Routes every occupant through the Axis-1 broadcast-exclusion registry
    (``flows.service_functions.perception_registry.resolve_broadcast_exclusions``) before it
    lands in ``sheets_by_room`` — a dreamside-perceiving occupant (or any other registered
    exclusion) must not receive waking-room ambient/risk-telegraph text, exactly like every
    other live room-broadcast call site. Resolved once per room, not once per session.
    """
    from evennia import SESSION_HANDLER  # noqa: PLC0415

    rooms: dict[int, DefaultObject] = {}
    sheets_by_room: dict[int, dict[int, CharacterSheet]] = {}
    excluded_by_room: dict[int, set[int]] = {}
    for session in SESSION_HANDLER.get_sessions():
        puppet = session.puppet
        if puppet is None:
            continue
        room = puppet.location
        if room is None:
            continue
        sheet = puppet.character_sheet
        if sheet is None:
            continue
        rooms.setdefault(room.pk, room)
        if room.pk not in excluded_by_room:
            excluded_by_room[room.pk] = {obj.pk for obj in resolve_broadcast_exclusions(room)}
        if puppet.pk in excluded_by_room[room.pk]:
            continue
        sheets_by_room.setdefault(room.pk, {})[sheet.pk] = sheet

    return rooms, {room_pk: list(sheets.values()) for room_pk, sheets in sheets_by_room.items()}


def roll_and_echo_ambient_texture() -> None:
    """Echo one ambient texture line to each online-occupied room, at IC phase boundaries.

    Checked every scheduler tick; no-ops unless the time-of-day phase transitioned since the
    last run (mirrors ``roll_and_echo_weather``'s #2845 guard, shared helper). On fire: derives
    the candidate room set from online sessions (Decision 5, never a grid scan), and for each
    such room selects and delivers one eligible ``AmbientEmit`` as a durable, squelchable
    ``ATMOSPHERE`` ``NarrativeMessage`` (never ``message_location`` — this is a systemic emit,
    not actor-driven scene text). Best-effort: a room with no eligible row simply gets nothing.
    """
    if not phase_transitioned_since_last_run(AMBIENT_TASK_KEY):
        return

    now = timezone.now()
    season = get_ic_season()
    phase = get_ic_phase()
    rooms, sheets_by_room = _online_occupied_rooms()
    for room_pk, room in rooms.items():
        emit = select_ambient_emit(room, season=season, phase=phase, now=now)
        if emit is None:
            continue
        recipients = sheets_by_room.get(room_pk, [])
        if not recipients:
            continue
        send_narrative_message(
            recipients=recipients,
            body=emit.text,
            category=NarrativeCategory.ATMOSPHERE,
            ooc_note="Ambient room texture (#2988).",
        )
        emit.last_fired_at = now
        emit.save(update_fields=["last_fired_at"])
