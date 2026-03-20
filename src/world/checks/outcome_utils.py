"""Shared utilities for processing check outcomes.

These are used by any system that maps check results to weighted consequences:
challenges, combat, magic, social scenes, etc.
"""

import random
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from world.checks.types import OutcomeDisplay

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

# Attribute names for duck-typed generic access
_ATTR_WEIGHT = "weight"
_ATTR_CHARACTER_LOSS = "character_loss"
_ATTR_LABEL = "label"
_ATTR_PK = "pk"
_ATTR_OUTCOME_TIER = "outcome_tier"
_ATTR_NAME = "name"


@runtime_checkable
class Weighted(Protocol):
    """Any object with a weight for random selection."""

    @property
    def weight(self) -> int: ...


@runtime_checkable
class CharacterLossProtected(Protocol):
    """Any object that may flag character loss."""

    @property
    def character_loss(self) -> bool: ...

    @property
    def weight(self) -> int: ...


def select_weighted[T](items: list[T]) -> T:
    """Select an item using weighted random. Items must have a .weight attribute."""
    weights = [getattr(item, _ATTR_WEIGHT, 1) or 1 for item in items]
    return random.choices(items, weights=weights, k=1)[0]  # noqa: S311


def filter_character_loss[T](
    character: "ObjectDB",
    selected: T,
    alternatives: list[T],
) -> T:
    """
    If selected item has character_loss=True and character has positive rollmod,
    replace with the worst non-loss alternative.

    Works with any object that has character_loss and weight attributes.
    Returns the original selection if no filtering applies.
    """
    if not getattr(selected, _ATTR_CHARACTER_LOSS, False):
        return selected

    from world.checks.services import get_rollmod  # noqa: PLC0415 — circular import

    rollmod = get_rollmod(character)
    if rollmod <= 0:
        return selected

    non_loss = [item for item in alternatives if not getattr(item, _ATTR_CHARACTER_LOSS, False)]
    if not non_loss:
        return selected

    # Select the worst non-loss alternative (lowest weight = least favorable)
    non_loss.sort(key=lambda item: getattr(item, _ATTR_WEIGHT, 1))
    return non_loss[0]


def build_outcome_display[T](
    all_items: list[T],
    selected: object,
    default_tier_name: str = "Unknown",
) -> list[OutcomeDisplay]:
    """
    Build roulette display payload from a list of weighted outcome items.

    Items must have .label, .outcome_tier.name, and .weight attributes.
    The selected item is marked with is_selected=True.
    """
    if not all_items:
        label = getattr(selected, _ATTR_LABEL, default_tier_name)
        return [
            OutcomeDisplay(
                label=label,
                tier_name=default_tier_name,
                weight=1,
                is_selected=True,
            )
        ]

    display: list[OutcomeDisplay] = []
    selected_pk = getattr(selected, _ATTR_PK, None)
    for item in all_items:
        item_pk = getattr(item, _ATTR_PK, None)
        if item_pk and selected_pk:
            is_selected = item_pk == selected_pk
        else:
            item_label = getattr(item, _ATTR_LABEL, None)
            sel_label = getattr(selected, _ATTR_LABEL, None)
            is_selected = item_label == sel_label
        tier_name = default_tier_name
        outcome_tier = getattr(item, _ATTR_OUTCOME_TIER, None)
        if outcome_tier:
            tier_name = str(getattr(outcome_tier, _ATTR_NAME, default_tier_name))
        display.append(
            OutcomeDisplay(
                label=item.label,
                tier_name=tier_name,
                weight=getattr(item, _ATTR_WEIGHT, 1) or 1,
                is_selected=is_selected,
            )
        )
    return display
