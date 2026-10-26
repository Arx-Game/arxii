"""Typed data structures for the covenants app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.covenants.models import CovenantRole, VowAddedEffect


@dataclass(frozen=True)
class CovenantFounder:
    """A single founder participating in covenant formation.

    Covenant formation requires at least two distinct founders — see
    `feedback_covenants_are_group_only.md`. The Sequence of founders passed
    to `create_covenant` becomes the initial set of memberships.

    ``is_leader`` marks this founder as the initial top-rank holder. At most
    one founder should be flagged; if none are, ``create_covenant`` defaults
    to the first founder.
    """

    character_sheet: CharacterSheet
    role: CovenantRole
    is_leader: bool = False


@dataclass(frozen=True)
class FiredVowEffect:
    """One ``VowAddedEffect`` that fires for a single cast, with its scaled bonuses (#4581).

    ``holder`` is the character whose vow carries the row: the caster for a
    SELF or WHOLE_GROUP row on the caster's own vow, a co-present covenant ally
    for a COVENANT_ALLIES or WHOLE_GROUP row on that ally's vow. ``is_secondary``
    is True when the row came from the holder's SECONDARY vow (#2641); its
    bonuses are then already scaled by ``SecondaryVowConfig.potency_tenths``.

    Each bonus is ``max(0, shown thread level - unlock_thread_level)`` times the
    row's matching ``*_per_thread_level`` column, read off the holder's
    COVENANT_ROLE thread on the vow's anchor role. ``severity_bonus`` and
    ``duration_bonus`` add to every applied condition; ``damage_bonus`` adds to
    every damage profile.
    """

    effect: VowAddedEffect
    holder: CharacterSheet
    is_secondary: bool
    severity_bonus: int
    duration_bonus: int
    damage_bonus: int
