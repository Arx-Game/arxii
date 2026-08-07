"""Level Stat Point services (#3001).

Every class level past the first grants one spendable stat point (level 1 is
the CG baseline). The balance is derived — ``level - 1`` minus active spends —
so no grant hook is needed on the level spine and a level reversal is
reconciled by :func:`sync_level_stat_point_spends`, never by deleting rows.
Caps reuse the authored ``MaturationStatCap`` table via ``stat_cap_for`` (the
ceiling is a property of the stage band, not of which point pool paid).
"""

from typing import TYPE_CHECKING

from django.db import transaction

from world.progression.exceptions import (
    StatPointCapReachedError,
    StatPointNoPointsError,
    StatPointNotAStatError,
)
from world.progression.models import LevelStatPointSpend
from world.progression.services.maturation import stat_cap_for
from world.progression.services.skill_development import get_character_path_level
from world.traits.constants import STAT_DISPLAY_DIVISOR
from world.traits.models import (
    CharacterTraitChange,
    CharacterTraitValue,
    Trait,
    TraitChangeSource,
    TraitType,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def stat_points_earned(level: int) -> int:
    """Points granted by ``level``: one per level past the first."""
    return max(0, level - 1)


def available_stat_points(sheet: "CharacterSheet") -> int:
    """Unspent level points at the sheet's current level."""
    level = get_character_path_level(sheet.character)
    spent = LevelStatPointSpend.objects.filter(
        character_sheet=sheet,
        level_granted__lte=level,
    ).count()
    return max(0, stat_points_earned(level) - spent)


def _granting_levels(level: int) -> list[int]:
    return list(range(2, level + 1))


@transaction.atomic
def spend_level_stat_point(sheet: "CharacterSheet", trait: Trait) -> LevelStatPointSpend:
    """Spend the lowest unspent level's point on +1 to ``trait``.

    Raises StatPointNotAStatError / StatPointNoPointsError /
    StatPointCapReachedError; the caller surfaces ``exc.user_message``.
    """
    if trait.trait_type != TraitType.STAT:
        raise StatPointNotAStatError(StatPointNotAStatError.user_message)
    if available_stat_points(sheet) <= 0:
        raise StatPointNoPointsError(StatPointNoPointsError.user_message)

    level = get_character_path_level(sheet.character)
    spent_levels = set(
        LevelStatPointSpend.objects.filter(character_sheet=sheet).values_list(
            "level_granted", flat=True
        )
    )
    unspent = [lvl for lvl in _granting_levels(level) if lvl not in spent_levels]
    if not unspent:
        raise StatPointNoPointsError(StatPointNoPointsError.user_message)

    trait_value, _ = CharacterTraitValue.objects.get_or_create(
        character=sheet, trait=trait, defaults={"value": 0}
    )
    # Caps are authored in display dots; stat storage is internal ×10 (#2894).
    cap = stat_cap_for(sheet)
    if cap is not None and trait_value.value >= cap * STAT_DISPLAY_DIVISOR:
        raise StatPointCapReachedError(StatPointCapReachedError.user_message)

    old_value = trait_value.value
    trait_value.value += STAT_DISPLAY_DIVISOR
    trait_value.save()
    CharacterTraitChange.objects.create(
        character_sheet=sheet,
        trait=trait,
        old_value=old_value,
        new_value=trait_value.value,
        source=TraitChangeSource.LEVEL_STAT_POINT,
    )
    return LevelStatPointSpend.objects.create(
        character_sheet=sheet,
        trait=trait,
        level_granted=unspent[0],
    )


@transaction.atomic
def sync_level_stat_point_spends(sheet: "CharacterSheet") -> int:
    """Reconcile spend activity with the sheet's current level.

    A spend whose granting level now exceeds the character's level goes
    dormant and its +1 comes off the stat; one that re-enters range
    reactivates. Mirrors ``sync_maturation_spends`` (explicit service calls,
    no signals; ADR-0009). Returns the number of spends flipped.
    """
    level = get_character_path_level(sheet.character)
    flipped = 0
    for spend in LevelStatPointSpend.objects.filter(character_sheet=sheet):
        should_be_active = spend.level_granted <= level
        if spend.is_active == should_be_active:
            continue
        delta = STAT_DISPLAY_DIVISOR if should_be_active else -STAT_DISPLAY_DIVISOR
        trait_value, _ = CharacterTraitValue.objects.get_or_create(
            character=sheet, trait=spend.trait, defaults={"value": 0}
        )
        old_value = trait_value.value
        trait_value.value += delta
        trait_value.save()
        CharacterTraitChange.objects.create(
            character_sheet=sheet,
            trait=spend.trait,
            old_value=old_value,
            new_value=trait_value.value,
            source=TraitChangeSource.LEVEL_STAT_POINT,
        )
        spend.is_active = should_be_active
        spend.save()
        flipped += 1
    return flipped
