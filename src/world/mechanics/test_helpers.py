"""Test helpers for the modifier system."""

from __future__ import annotations

from world.character_sheets.models import CharacterSheet
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
from world.mechanics.factories import (
    CharacterModifierFactory,
    DistinctionModifierSourceFactory,
    ModifierCategoryFactory,
    ModifierTargetFactory,
)
from world.mechanics.models import CharacterModifier, ModifierTarget


def lever_target(category_name: str, target_name: str) -> ModifierTarget:
    """The authored lever target, created if the test database lacks it (#4394)."""
    return ModifierTargetFactory(
        category=ModifierCategoryFactory(name=category_name), name=target_name
    )


def grant_lever(
    sheet: CharacterSheet, category_name: str, target_name: str, value: int
) -> CharacterModifier:
    """Give ``sheet`` a distinction-backed modifier of ``value`` on a lever target (#4394).

    Bare ``ModifierSource`` rows contribute nothing to a total (#909), so the grant rides a
    distinction effect the way an authored distinction's would.
    """
    target = lever_target(category_name, target_name)
    distinction = DistinctionFactory()
    effect = DistinctionEffectFactory(distinction=distinction, target=target, value_per_rank=value)
    source = DistinctionModifierSourceFactory(
        distinction_effect=effect,
        character_distinction=CharacterDistinctionFactory(character=sheet, distinction=distinction),
    )
    return CharacterModifierFactory(character=sheet, value=value, source=source, target=target)
