"""Player-facing heat surfaces (#1765) — always self-only.

Heat is risk information for the hunted persona alone: these helpers resolve
the *viewing* character's active persona and never render another character's
pursuit picture (leak table on the issue). Copy is PLACEHOLDER pending the
voice pass; tier colours are the ratified ladder direction (green → red).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.justice.constants import HeatTier
from world.justice.services import heat_for

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.justice.types import HeatReading

# PLACEHOLDER copy + colours for the telnet line, keyed by tier.
_TIER_LINES: dict[HeatTier, str] = {
    HeatTier.WATCHED: "|yPLACEHOLDER: Someone here has been asking about you.|n",
    HeatTier.HUNTED: "|530PLACEHOLDER: The watch is looking for you here.|n",
    HeatTier.HEAT_IS_ON: "|rPLACEHOLDER: The heat is on — guards actively hunt you in this area.|n",
    HeatTier.EXTREME_HEAT: (
        "|RPLACEHOLDER: Guards are searching everyone nearby — discovery could be imminent.|n"
    ),
}

# PLACEHOLDER relief line for crossing into safety.
_SAFE_TRANSITION_LINE = "|gPLACEHOLDER: You breathe easier — no one hunts you here.|n"


def heat_reading_for_character(character: ObjectDB, room: ObjectDB | None) -> HeatReading | None:
    """The viewing character's own pursuit picture at ``room``, or None when unresolvable."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = getattr(character, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if sheet is None or room is None:
        return None
    try:
        persona = active_persona_for_sheet(sheet)
    except ObjectDoesNotExist:
        # A sheet with no persona yet (pre-CG, NPC shells) simply has no heat surface.
        return None
    if persona is None:
        return None
    return heat_for(persona, room)


def room_heat_line(character: ObjectDB, room: ObjectDB | None) -> str | None:
    """The self-only appended room-desc line — None when SAFE (no line at all)."""
    reading = heat_reading_for_character(character, room)
    if reading is None or reading.is_safe:
        return None
    return _TIER_LINES.get(reading.tier)


def room_heat_payload(character: ObjectDB, room: ObjectDB | None) -> dict[str, str] | None:
    """The web room-state field: ``{"tier", "label"}`` — None when SAFE (field omitted)."""
    reading = heat_reading_for_character(character, room)
    if reading is None or reading.is_safe:
        return None
    return {"tier": reading.tier.value, "label": reading.tier.label}


def safe_transition_line(
    character: ObjectDB, source: ObjectDB | None, destination: ObjectDB | None
) -> str | None:
    """The relief line when a hot persona crosses into safety (user-ratified surface).

    Fires only on a real drop — the source read at or above HEAT_IS_ON and the
    destination fully SAFE — so ordinary moves between cold rooms stay silent.
    """
    destination_reading = heat_reading_for_character(character, destination)
    if destination_reading is None or not destination_reading.is_safe:
        return None
    source_reading = heat_reading_for_character(character, source)
    if source_reading is None:
        return None
    hot_tiers = (HeatTier.HEAT_IS_ON, HeatTier.EXTREME_HEAT)
    if source_reading.tier not in hot_tiers:
        return None
    return _SAFE_TRANSITION_LINE
