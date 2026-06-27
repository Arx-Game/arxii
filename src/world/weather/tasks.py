"""Periodic weather tasks (#1522), registered with the ``game_clock`` scheduler.

The weather tick runs every 2 real hours (≈6 IC hours at the default 3× ratio): it rerolls each
climate-bearing region's weather and echoes one season/phase-appropriate line to the online
characters in that region's rooms, as an ``ATMOSPHERE`` narrative message (so the frontend can
route it to a tab and players can squelch it). Best-effort and quiet.
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


def _online_recipients(room: DefaultObject) -> list[CharacterSheet]:
    """CharacterSheets of *online* characters in a room (offline players skip the echo)."""
    recipients: list[CharacterSheet] = []
    for obj in room.contents:
        if not obj.sessions.count():
            continue
        sheet = getattr(obj, "sheet_data", None)  # noqa: GETATTR_LITERAL
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


def roll_and_echo_weather() -> None:
    """Reroll each climate-bearing region's weather and echo it to online occupants (#1522).

    The 2-real-hour weather tick. On a **feast day** (Eclipse / Moon Madness), the special
    weather is forced world-wide, overriding the normal climate-gated roll — the automation that
    replaces a GM pulling the lever. Best-effort: a region with no eligible weather or no online
    occupants simply emits nothing. Weather attaches to climate-bearing regions; sub-regions
    inherit via the most-specific-wins resolver.
    """
    special = special_weather_for_today()
    for region in Area.objects.filter(climate__isnull=False):
        roll_region_weather(region, weather_type=special)
        _echo_region_weather(region)
