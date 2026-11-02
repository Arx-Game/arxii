"""How a combat style attacks and defends, as the pages that show a style read it (#4921).

Character creation's style step and the character sheet both show a style's weapon kinds
(its attack profile) and armor kinds (its defense profile) by their ``GearArchetype``
labels, in that enum's order. Never its vows: creation never mentions covenant vows, and
the Sphinx is where a player learns which vows a style suits.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypedDict

from world.items.constants import ARMOR_ARCHETYPES, WEAPON_ARCHETYPES, GearArchetype


class GearKindLabel(TypedDict):
    """One weapon or armor kind: its stored value and its label."""

    value: str
    label: str


def _kinds(held: Iterable[str], wanted: frozenset[str]) -> list[GearKindLabel]:
    held_set = set(held)
    return [
        GearKindLabel(value=value, label=label)
        for value, label in GearArchetype.choices
        if value in held_set and value in wanted
    ]


def weapon_kinds(held: Iterable[str]) -> list[GearKindLabel]:
    """The weapon kinds among a style's gear kinds ``held``."""
    return _kinds(held, WEAPON_ARCHETYPES)


def armor_kinds(held: Iterable[str]) -> list[GearKindLabel]:
    """The armor kinds among a style's gear kinds ``held``."""
    return _kinds(held, ARMOR_ARCHETYPES)
