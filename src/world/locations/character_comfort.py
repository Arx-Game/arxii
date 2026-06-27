"""Per-character comfort readout (#1522/#1514).

How uncomfortable a *character* is in their current room, and why — the room's felt exposure on
each axis MINUS what their worn clothing (and resonance-imbued garments) mitigate (floored at 0
per axis), plus an injury penalty, mapped to a named band with the biting reasons.

Distinct from the room's own comfort (``services.comfort_summary``): a fur coat doesn't warm the
*room*, it warms *you*. Worn-item mitigation is read off the wearer's ``items.EquippedItem`` rows
(lazy-imported to keep the dependency one-way). Magnitudes/bands are PLACEHOLDER author passes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from django.core.exceptions import ObjectDoesNotExist

from world.locations.constants import (
    COMFORT_BAND_FLOORS,
    EXPOSURE_REASON_WORDS,
    EXPOSURE_STAT_KEYS,
    INJURY_DISCOMFORT_MAX,
    StatKey,
)
from world.locations.services import felt_exposure

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject


class CharacterComfortSummary(NamedTuple):
    """A character's personal comfort readout (#1522)."""

    band: str  # e.g. "Very uncomfortable"
    band_index: int  # 0 (Comfortable) … 4 (Extremely uncomfortable), for ordering/web
    discomfort: int  # total felt discomfort after clothing + injury
    reasons: list[str]  # what's biting, worst-first: e.g. ["cold", "injured"]
    felt: dict[StatKey, int]  # per-axis residual felt exposure (nonzero only)
    injury: int  # injury's contribution to discomfort


def worn_exposure_mitigation(character: DefaultObject) -> dict[StatKey, int]:
    """Total per-axis exposure a character's worn garments mitigate (#1522).

    Sums ``GarmentMitigation`` rows (mundane + resonance-imbued) across every currently worn item.
    """
    from world.items.models import EquippedItem, GarmentMitigation  # noqa: PLC0415

    template_ids = list(
        EquippedItem.objects.filter(character=character).values_list(
            "item_instance__template_id", flat=True
        )
    )
    mitigation: dict[StatKey, int] = {}
    if not template_ids:
        return mitigation
    for row in GarmentMitigation.objects.filter(item_template_id__in=template_ids):
        key = StatKey(row.stat_key)
        mitigation[key] = mitigation.get(key, 0) + row.value
    return mitigation


def injury_discomfort(character: DefaultObject) -> int:
    """Extra discomfort from injury — scales with how far below full health the character is."""
    sheet = getattr(character, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if sheet is None:
        return 0
    try:
        vitals = sheet.vitals
    except (AttributeError, ObjectDoesNotExist):
        return 0
    return round((1.0 - vitals.health_percentage) * INJURY_DISCOMFORT_MAX)


def _band_for(discomfort: int) -> tuple[int, str]:
    """The (index, label) of the highest comfort band whose floor ``discomfort`` meets."""
    chosen_index, chosen_label = 0, COMFORT_BAND_FLOORS[0][1]
    for index, (floor, label) in enumerate(COMFORT_BAND_FLOORS):
        if discomfort >= floor:
            chosen_index, chosen_label = index, label
    return chosen_index, chosen_label


def character_comfort_summary(character: DefaultObject) -> CharacterComfortSummary:
    """A character's personal comfort in their current room (#1522).

    Per axis: ``residual = max(0, room felt_exposure − worn mitigation)`` (a coat reduces what *you*
    feel, floored — never makes you colder or touches another axis). Sums the residuals + an injury
    penalty, resolves the named band, and reports the biting axes (worst-first) as the "why".
    """
    room = character.location
    if room is None:
        index, label = _band_for(0)
        return CharacterComfortSummary(label, index, 0, [], {}, 0)

    mitigation = worn_exposure_mitigation(character)
    felt: dict[StatKey, int] = {}
    for axis in EXPOSURE_STAT_KEYS:
        residual = max(0, felt_exposure(room, stat_key=axis) - mitigation.get(axis, 0))
        if residual:
            felt[axis] = residual

    injury = injury_discomfort(character)
    discomfort = sum(felt.values()) + injury
    index, label = _band_for(discomfort)

    worst_first = sorted(felt, key=lambda axis: felt[axis], reverse=True)
    reasons = [EXPOSURE_REASON_WORDS[axis] for axis in worst_first]
    if injury:
        reasons.append("injured")
    return CharacterComfortSummary(label, index, discomfort, reasons, felt, injury)
