"""Kindled resonance result types (#5124).

``KindlingAct`` is what the character did, handed to the kindling situations so they can say
whether the act feeds a resonance. ``KindledResonance`` is one resonance's answer: kindled or
not, how strongly, and why in player words. Nothing here is stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import KindledStrengthTier, KindlingSituation, Resonance
    from world.missions.models import MissionOption


@dataclass(frozen=True)
class KindlingAct:
    """One act of the character, as the kindling situations read it.

    ``kind`` is a ``KindlingActKind`` value. ``aids`` is true when the act helps someone
    (cover, interpose, succor, a heal, freeing them).
    """

    kind: str
    target: CharacterSheet | None = None
    mission_option: MissionOption | None = None
    aids: bool = False


@dataclass(frozen=True)
class KindlingEvidence:
    """One thing that made a situation hold, with what reaches a strength from it.

    ``bond_tier`` and ``severity`` are 0 when the evidence has none; a strength tier is
    reached through them only where its own reach column is above 0. ``reason`` is the line
    a player reads.
    """

    reason: str
    bond_tier: int = 0
    severity: int = 0


@dataclass(frozen=True)
class KindledResonance:
    """One resonance the character holds, and whether a situation kindles it now.

    ``tier is None`` means not kindled. ``situations`` are the authored rows that kindled it,
    strongest first; ``reasons`` are the player-word lines, strongest first, with no numbers.
    A kindling that came from a Rally or a GM adds a reason and may set the tier but names no
    situation.
    """

    resonance: Resonance
    tier: KindledStrengthTier | None
    reasons: tuple[str, ...]
    situations: tuple[KindlingSituation, ...]

    @property
    def is_kindled(self) -> bool:
        return self.tier is not None

    @property
    def strongest_situation(self) -> KindlingSituation | None:
        """The authored row that kindled it most strongly, or None (a Rally or a GM only)."""
        return self.situations[0] if self.situations else None
