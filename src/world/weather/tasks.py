"""Periodic weather tasks (#1522, phase-aligned #2845), registered with the ``game_clock``
scheduler.

The weather tick is checked every scheduler tick but FIRES only when the IC time-of-day phase
transitions (dawn/day/dusk/night, #2845): it rerolls each climate-bearing region's weather and
echoes one season/phase-appropriate line to the online characters in that region's rooms, as a
``WEATHER`` narrative message (so the frontend can route it to a tab and players can squelch
it). Rolling AT the boundary means the echo always describes the phase that just began —
morning lines at dawn, night lines at nightfall — instead of landing mid-phase off a
wall-clock interval. Four transitions per IC day ≈ the old 2-real-hour cadence at the default
3x ratio, so churn is unchanged. Best-effort and quiet.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.areas.models import Area
from world.areas.services import get_rooms_in_area
from world.narrative.constants import NarrativeCategory
from world.narrative.services import send_narrative_message
from world.weather.services import (
    roll_region_weather,
    select_weather_emit,
    special_weather_for_today,
)

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

    from world.character_sheets.models import CharacterSheet

logger = logging.getLogger("world.weather")

WEATHER_TASK_KEY = "weather.roll"


def _online_recipients(room: DefaultObject) -> list[CharacterSheet]:
    """CharacterSheets of *online* characters in a room (offline players skip the echo)."""
    recipients: list[CharacterSheet] = []
    for obj in room.contents:
        if not obj.sessions.count():
            continue
        sheet = obj.character_sheet
        if sheet is not None:
            recipients.append(sheet)
    return recipients


def _echo_region_weather(region: Area) -> None:
    """Push one weather emit to the online occupants of a region's rooms (#1522)."""
    emit = select_weather_emit(region)
    if emit is None:
        return
    recipients: list[CharacterSheet] = []
    for profile in get_rooms_in_area(region):
        recipients.extend(_online_recipients(profile.objectdb))
    if not recipients:
        return
    send_narrative_message(
        recipients=recipients,
        body=emit.text,
        category=NarrativeCategory.WEATHER,
        ooc_note="Weather echo (#1522).",
    )


def _phase_transitioned_since_last_run() -> bool:
    """Whether the IC time-of-day phase changed since this task's last stamped run (#2845).

    Thin wrapper over the shared ``game_clock.task_registry.phase_transitioned_since_last_run``
    (extracted #2988 so the ambient-texture roll can share the exact guard shape against its
    own task key) — see that function's docstring for the full behavior.
    """
    from world.game_clock.task_registry import phase_transitioned_since_last_run  # noqa: PLC0415

    return phase_transitioned_since_last_run(WEATHER_TASK_KEY)


def roll_and_echo_weather() -> None:
    """Reroll each climate-bearing region's weather and echo it, at IC phase boundaries.

    Checked every scheduler tick; no-ops unless the time-of-day phase transitioned since
    the last run (#2845), so the roll + phase-gated echo land right as dawn/day/dusk/night
    begins. On a **feast day** (Eclipse / Moon Madness), the special weather is forced
    world-wide, overriding the normal climate-gated roll — the automation that replaces a
    GM pulling the lever. Best-effort: a region with no eligible weather or no online
    occupants simply emits nothing. Weather attaches to climate-bearing regions;
    sub-regions inherit via the most-specific-wins resolver.
    """
    if not _phase_transitioned_since_last_run():
        return
    special = special_weather_for_today()
    for region in Area.objects.filter(climate__isnull=False):
        roll_region_weather(region, weather_type=special)
        _echo_region_weather(region)
