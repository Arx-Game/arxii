"""Typed data structures for the covenants app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.covenants.models import CovenantRole


@dataclass(frozen=True)
class CovenantFounder:
    """A single founder participating in covenant formation.

    Covenant formation requires at least two distinct founders — see
    `feedback_covenants_are_group_only.md`. The Sequence of founders passed
    to `create_covenant` becomes the initial set of memberships.
    """

    character_sheet: CharacterSheet
    role: CovenantRole
