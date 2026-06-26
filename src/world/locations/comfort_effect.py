"""Comfort → AP-regen effect (#1514).

Residents of a comfortable home regenerate AP faster; an uncomfortable one slower. The
**efficient** path: comfort is materialized as a flat additive ``CharacterModifier`` on the
``ap_daily_regen`` / ``ap_weekly_regen`` targets (delta = ``comfort_level − 5``), recomputed
ONLY on the discrete events that change a character's home comfort — never at regen time, where
the cron already reads pre-summed modifier totals in one query.

Triggers (all explicit calls, no signals): a character's home changing
(``set_residence`` / ``maybe_default_residence``), and the home-room's comfort changing
(``set_building_style``, ``place_decoration`` / ``remove_decoration``; the future weather tick).
The reverse "who lives here" lookup is one indexed ``ObjectDB.db_home`` query.

The mechanics touch is one shared ``ModifierSource`` (``residence_comfort=True``) — flagged for
TehomCD as modifier-system territory; it's additive and self-contained.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.locations.constants import (
    AP_MODIFIER_CATEGORY,
    AP_REGEN_TARGET_NAMES,
    COMFORT_LEVEL_NEUTRAL,
)
from world.locations.services import comfort_level

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

    from world.character_sheets.models import CharacterSheet
    from world.mechanics.models import ModifierSource, ModifierTarget


def _comfort_source() -> ModifierSource:
    """The single shared ``ModifierSource`` for residence-comfort modifiers (#1514)."""
    from world.mechanics.models import ModifierSource  # noqa: PLC0415

    source, _ = ModifierSource.objects.get_or_create(residence_comfort=True)
    return source


def _ap_regen_targets() -> list[ModifierTarget]:
    """The ap-regen ``ModifierTarget``s, created on demand (only seeded in tests otherwise)."""
    from world.mechanics.models import ModifierCategory, ModifierTarget  # noqa: PLC0415

    category, _ = ModifierCategory.objects.get_or_create(name=AP_MODIFIER_CATEGORY)
    return [
        ModifierTarget.objects.get_or_create(name=name, category=category)[0]
        for name in AP_REGEN_TARGET_NAMES
    ]


def _sheet_for(character: DefaultObject) -> CharacterSheet | None:
    """The character's CharacterSheet, or None (non-character objects fall through)."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        return character.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None


def comfort_regen_delta_for_room(room: DefaultObject) -> int:
    """The flat AP-regen delta a resident of this room earns (#1514): ``comfort_level − 5``."""
    return comfort_level(room) - COMFORT_LEVEL_NEUTRAL


def recompute_comfort_regen_modifier(character: DefaultObject) -> None:
    """Re-materialize a character's residence-comfort AP-regen modifier (#1514).

    Reads the comfort of their home and writes a flat ``CharacterModifier`` (delta on each
    ap-regen target), or clears it when they have no real residence / the delta is 0. Idempotent;
    the regen cron then reads it for free.
    """
    from world.mechanics.models import CharacterModifier  # noqa: PLC0415

    sheet = _sheet_for(character)
    if sheet is None:
        return
    home = character.home
    delta = comfort_regen_delta_for_room(home) if home is not None else 0
    source = _comfort_source()
    for target in _ap_regen_targets():
        if delta:
            CharacterModifier.objects.update_or_create(
                character=sheet, target=target, source=source, defaults={"value": delta}
            )
        else:
            CharacterModifier.objects.filter(character=sheet, target=target, source=source).delete()


def recompute_room_residents_comfort(room: DefaultObject) -> None:
    """Bulk-recompute comfort modifiers for everyone whose home is this room (#1514).

    One indexed ``db_home`` query, then per-resident recompute. Called when a room's comfort
    changes (style / decoration / weather), so residents' AP regen tracks it without any work
    at regen time.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    for resident in ObjectDB.objects.filter(db_home=room):
        recompute_comfort_regen_modifier(resident)
