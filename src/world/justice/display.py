"""Player-facing heat surfaces (#1765) — always self-only.

Heat is risk information for the hunted persona alone: these helpers resolve
the *viewing* character's active persona and never render another character's
pursuit picture (leak table on the issue). Copy approved by Apostate
(2026-07-03; no em-dashes in player-facing lines); tier colours are the
ratified ladder direction (green → red). The Dangerous line names the local
enforcers via ``Society.enforcer_name`` (Luxen: "The Honest have been looking
for you here").
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.justice.constants import HeatTier
from world.justice.services import heat_for

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.justice.types import HeatReading

# Approved copy, keyed by tier. {enforcer} = the local Society.enforcer_name.
_TIER_LINES: dict[HeatTier, str] = {
    HeatTier.TENSE: "|ySomeone here has been asking about you.|n",
    HeatTier.DANGEROUS: "|530{enforcer} have been looking for you here.|n",
    HeatTier.HEAT_IS_ON: "|rThe heat is on; {enforcer} actively hunt you in this area.|n",
    HeatTier.EXTREME_HEAT: (
        "|R{enforcer} are searching everyone nearby; discovery could be imminent.|n"
    ),
}

# The relief line for crossing into safety.
_SAFE_TRANSITION_LINE = "|gYou breathe easier; no one hunts you here.|n"


def heat_reading_for_character(character: ObjectDB, room: ObjectDB | None) -> HeatReading | None:
    """The viewing character's own pursuit picture at ``room``, or None when unresolvable."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = character.character_sheet
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


def _local_enforcer_name(room: ObjectDB | None) -> str:
    from world.justice.services import area_for_room, enforcing_society_for  # noqa: PLC0415

    society = enforcing_society_for(area_for_room(room)) if room is not None else None
    return society.enforcer_name if society is not None else "The Watch"


def room_heat_line(character: ObjectDB, room: ObjectDB | None) -> str | None:
    """The self-only appended room-desc line — None when SAFE (no line at all)."""
    reading = heat_reading_for_character(character, room)
    if reading is None or reading.is_safe:
        return None
    line = _TIER_LINES.get(reading.tier)
    if line is None:
        return None
    return line.format(enforcer=_local_enforcer_name(room))


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
