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
    from world.checks.models import CheckType
    from world.magic.models import KindledStrengthTier, KindlingSituation, Resonance
    from world.missions.models import MissionOption


@dataclass(frozen=True)
class KindlingAct:
    """One act of the character, as the kindling situations read it.

    ``kind`` is a ``KindlingActKind`` value. ``aids`` is true when the act helps someone
    (cover, interpose, succor, a heal, freeing them). ``label`` is the act in the player's
    own words (the mission option's title, the technique's name, "Struck the bandit"); a
    deed grant records it so the character can tell one deed from another later.

    ``category`` is the fatigue pool a gain from this act charges (an ``ActionCategory``
    value); blank means the one its ``kind`` implies (``act_fatigue_category``). ``check_type``
    is the act's own roll, whose heaviest stat the bonus resonance check borrows (#5327).
    """

    kind: str
    target: CharacterSheet | None = None
    mission_option: MissionOption | None = None
    aids: bool = False
    label: str = ""
    category: str = ""
    check_type: CheckType | None = None


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

    ``fed_tier`` and ``fed_reasons`` are the part authored situations account for: the
    strength of the strongest row that held (with the act, when one was given) and the
    reasons of the rows only. A Rally or GM raises ``tier`` but never these, so what an act
    earns and what an option promises read them, never the Rally or GM strength.

    ``chosen_tier``, ``chosen_situation`` and ``chosen_reasons`` are the narrower part that
    authored choice rows alone reach (``CHOSEN_DEED_SITUATIONS``: a mission option's theme).
    Only these pay at once; every other row feeds ``fed_*`` and so suggests the resonance and
    strengthens it, and never pays (#5327).
    """

    resonance: Resonance
    tier: KindledStrengthTier | None
    reasons: tuple[str, ...]
    situations: tuple[KindlingSituation, ...]
    fed_tier: KindledStrengthTier | None = None
    fed_reasons: tuple[str, ...] = ()
    chosen_tier: KindledStrengthTier | None = None
    chosen_situation: KindlingSituation | None = None
    chosen_reasons: tuple[str, ...] = ()

    @property
    def is_kindled(self) -> bool:
        return self.tier is not None

    @property
    def strongest_situation(self) -> KindlingSituation | None:
        """The authored row that kindled it most strongly, or None (a Rally or a GM only)."""
        return self.situations[0] if self.situations else None


@dataclass(frozen=True)
class PendingReach:
    """A checked reach a pose carries, waiting for the pose to post (#5308).

    ``resonance_id`` is the resonance the pose reaches for. Any resonance is valid, held or not.
    """

    resonance_id: int
