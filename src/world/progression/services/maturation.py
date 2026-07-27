"""Maturation Point services (#2756).

Deterministic milestones: one point per matured-year 21, 24, 27, ... A spend
is active iff its milestone_year <= the sheet's matured_years; reversal and
re-aging are handled by :func:`sync_maturation_spends`, never by deleting
spend rows.
"""

from typing import TYPE_CHECKING

from django.db import transaction

from world.classes.services import stage_for_level
from world.progression.constants import MATURATION_INTERVAL_YEARS, MATURATION_START_YEAR
from world.progression.exceptions import (
    MaturationCapReachedError,
    MaturationNoPointsError,
    MaturationNotAStatError,
)
from world.progression.models import MaturationSpend, MaturationStatCap
from world.progression.services.skill_development import get_character_path_level
from world.traits.models import CharacterTraitValue, Trait, TraitType

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def milestone_count(matured_years: int) -> int:
    """Milestones earned by ``matured_years``: 0 below 21, then one per 3 years."""
    if matured_years < MATURATION_START_YEAR:
        return 0
    return (matured_years - (MATURATION_START_YEAR - MATURATION_INTERVAL_YEARS)) // (
        MATURATION_INTERVAL_YEARS
    )


def _earns_maturation(sheet: "CharacterSheet") -> bool:
    """Eternal-youth species never earn points (Decision 6, #2756)."""
    species = sheet.species
    return not (species is not None and species.eternal_youth)


def available_points(sheet: "CharacterSheet") -> int:
    """Unspent milestones at the sheet's current matured years."""
    if not _earns_maturation(sheet):
        return 0
    spent = MaturationSpend.objects.filter(
        character_sheet=sheet,
        milestone_year__lte=sheet.matured_years,
    ).count()
    return max(0, milestone_count(sheet.matured_years) - spent)


def _milestone_years(matured_years: int) -> list[int]:
    return list(range(MATURATION_START_YEAR, matured_years + 1, MATURATION_INTERVAL_YEARS))


def stat_cap_for(sheet: "CharacterSheet") -> int | None:
    """The per-stat cap for the sheet's current stage, or None when unauthored."""
    character = sheet.character
    level = get_character_path_level(character)
    stage = stage_for_level(level)
    row = MaturationStatCap.objects.filter(path_stage=stage).first()
    return row.stat_cap if row else None


@transaction.atomic
def spend_maturation_point(sheet: "CharacterSheet", trait: Trait) -> MaturationSpend:
    """Spend the lowest unspent milestone on +1 to ``trait``.

    Raises MaturationNotAStatError / MaturationNoPointsError /
    MaturationCapReachedError; the caller surfaces ``exc.user_message``.
    """
    if trait.trait_type != TraitType.STAT:
        raise MaturationNotAStatError(MaturationNotAStatError.user_message)
    if available_points(sheet) <= 0:
        raise MaturationNoPointsError(MaturationNoPointsError.user_message)

    spent_years = set(
        MaturationSpend.objects.filter(character_sheet=sheet).values_list(
            "milestone_year", flat=True
        )
    )
    unspent = [y for y in _milestone_years(sheet.matured_years) if y not in spent_years]
    if not unspent:
        raise MaturationNoPointsError(MaturationNoPointsError.user_message)

    trait_value, _ = CharacterTraitValue.objects.get_or_create(
        character=sheet, trait=trait, defaults={"value": 0}
    )
    cap = stat_cap_for(sheet)
    if cap is not None and trait_value.value >= cap:
        raise MaturationCapReachedError(MaturationCapReachedError.user_message)

    trait_value.value += 1
    trait_value.save()
    return MaturationSpend.objects.create(
        character_sheet=sheet,
        trait=trait,
        milestone_year=unspent[0],
    )


@transaction.atomic
def sync_maturation_spends(sheet: "CharacterSheet") -> int:
    """Reconcile spend activity with the sheet's current matured years.

    A spend whose milestone_year now exceeds matured_years goes dormant and
    its +1 comes off the stat; one that re-enters range reactivates and the
    +1 returns. Every writer of ``matured_years`` outside the birthday tick
    must call this. Returns the number of spends flipped.
    """
    flipped = 0
    spends = MaturationSpend.objects.filter(character_sheet=sheet)
    for spend in spends:
        should_be_active = spend.milestone_year <= sheet.matured_years
        if spend.is_active == should_be_active:
            continue
        delta = 1 if should_be_active else -1
        trait_value, _ = CharacterTraitValue.objects.get_or_create(
            character=sheet, trait=spend.trait, defaults={"value": 0}
        )
        trait_value.value += delta
        trait_value.save()
        spend.is_active = should_be_active
        spend.save()
        flipped += 1
    return flipped
