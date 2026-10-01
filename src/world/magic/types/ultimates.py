"""Reveal value types for ultimates (#4098)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.classes.models import Path
    from world.companions.models import Companion
    from world.magic.models import Gift, KnownUltimate, Technique
    from world.worship.models import WorshippedBeing


@dataclass(frozen=True)
class UltimateRevealCard:
    """One card. ``technique`` is None for a CATEGORY card (never leaked)."""

    choice_key: str
    kind: str
    category: str
    label: str
    technique: Technique | None = None
    upgrade_of: Technique | None = None


@dataclass(frozen=True)
class UltimateRevealGroup:
    source: str
    source_id: int
    cards: tuple[UltimateRevealCard, ...]
    path: Path | None = None
    gift: Gift | None = None
    being: WorshippedBeing | None = None
    companion: Companion | None = None


@dataclass(frozen=True)
class UltimateReveal:
    ceremony: str
    framing_text: str
    groups: tuple[UltimateRevealGroup, ...]
    sheet: CharacterSheet | None = None

    def flat_cards(self) -> list[tuple[UltimateRevealGroup, UltimateRevealCard]]:
        """Stable order shared by web and telnet numbering."""
        return [(group, card) for group in self.groups for card in group.cards]


@dataclass(frozen=True)
class AudereUltimateState:
    reveal: UltimateReveal | None
    readied: KnownUltimate | None
    deferred_death_text: str
