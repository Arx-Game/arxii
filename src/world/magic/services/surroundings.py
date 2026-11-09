"""A technique that needs surroundings its own gift does not make (#5018, slice 4).

A DESIGN ``Restriction`` may name a room reading and bounds (wet air for a storm
technique). It is never a refusal: unmet, the cast's roll takes one heavy, named
"Surroundings" penalty, sized as a share of a typical roll at the caster's level. On a
technique whose own gift's substance is that reading it does nothing, since every cast of
that gift already needs its substance (``world.magic.services.substance``).

``cast_surroundings_lines`` is what the cast card shows under its cost: the substance
plan's lines plus any unmet restriction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.checks.constants import ModifierSourceKind
from world.checks.types import ModifierContribution
from world.locations.constants import StatKey
from world.locations.services import felt_exposure
from world.magic.constants import RestrictionKind
from world.magic.types.substance import SurroundingsKind, SurroundingsLine

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.magic.models import Restriction, Technique
    from world.magic.types.substance import SubstancePlan


@dataclass(frozen=True)
class UnmetSurroundings:
    """One surroundings restriction the room does not meet."""

    restriction: Restriction
    reading: int


def _reading_word(stat_key: StatKey, value: int) -> str:
    """A plain word for where the reading sits, for the roll line."""
    if stat_key == StatKey.LIGHTING:
        return {-2: "pitch dark", -1: "dim", 0: "ordinary light", 1: "bright", 2: "blinding"}.get(
            value, str(value)
        )
    if value == 0:
        return {StatKey.WET: "dry", StatKey.WIND: "still air"}.get(stat_key, "none")
    return f"{stat_key.label.lower()} {value}"


def unmet_surroundings(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - a caster
    technique: Technique,
) -> list[UnmetSurroundings]:
    """The technique's surroundings restrictions the caster's room fails. Never raises."""
    from world.magic.services.substance import substance_for_gift  # noqa: PLC0415

    restrictions = [
        r
        for r in technique.cached_restrictions
        if r.kind == RestrictionKind.DESIGN and r.surroundings_stat
    ]
    room = character.location
    if not restrictions or room is None:
        return []
    own = substance_for_gift(technique.gift)
    unmet: list[UnmetSurroundings] = []
    for restriction in restrictions:
        if own is not None and own.stat_key == restriction.surroundings_stat:
            continue
        value = felt_exposure(room, stat_key=StatKey(restriction.surroundings_stat))
        low, high = restriction.surroundings_min, restriction.surroundings_max
        if (low is not None and value < low) or (high is not None and value > high):
            unmet.append(UnmetSurroundings(restriction=restriction, reading=value))
    return unmet


def _penalty(character: ObjectDB) -> int:  # noqa: OBJECTDB_PARAM - a caster
    """One typical roll at her level, times the configured percent (a negative number)."""
    from world.checks.modifier_values import level_baseline  # noqa: PLC0415
    from world.magic.services.resonance_environment import (  # noqa: PLC0415
        get_resonance_environment_config,
    )
    from world.magic.services.techniques import _get_character_sheet  # noqa: PLC0415

    sheet = _get_character_sheet(character)
    level = sheet.current_level if sheet is not None else 1
    baseline = level_baseline(level) or 0
    pct = get_resonance_environment_config().unmet_surroundings_penalty_pct
    return -round(baseline * pct / 100)


def surroundings_contributions(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - a caster
    technique: Technique | None,
) -> list[ModifierContribution]:
    """The roll lines for unmet surroundings: one SCENE ("Surroundings") line each."""
    if technique is None:
        return []
    unmet = unmet_surroundings(character, technique)
    if not unmet:
        return []
    penalty = _penalty(character)
    return [
        ModifierContribution(
            source_kind=ModifierSourceKind.SCENE,
            source_label=(
                f"Surroundings: {item.restriction.name} (here: "
                f"{_reading_word(StatKey(item.restriction.surroundings_stat), item.reading)})"
            ),
            value=penalty,
        )
        for item in unmet
    ]


def cast_surroundings_lines(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - a caster
    technique: Technique,
    plan: SubstancePlan,
) -> list[SurroundingsLine]:
    """Everything the cast card shows under its cost about where she stands (#5018)."""
    from world.magic.services.substance import surroundings_lines  # noqa: PLC0415

    lines = surroundings_lines(plan)
    for item in unmet_surroundings(character, technique):
        lines.append(
            SurroundingsLine(
                kind=SurroundingsKind.NEEDS,
                text=f"{item.restriction.name}: very heavy penalty here",
                amount=_penalty(character),
            )
        )
    return lines
