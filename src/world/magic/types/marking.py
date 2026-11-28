"""Marking result types (#5327).

``PendingMark`` is a checked mark a pose or journal entry carries, waiting for the writing to be
saved. ``MarkResult`` is what recording it left. ``WeeklyStanding`` is where a character stands
on the weekly table of marks. ``GainFatigueCharge`` is what charging a gain's fatigue did to the
gain. Nothing here is stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import ResonanceGrant


@dataclass(frozen=True)
class PendingMark:
    """A checked mark waiting for its pose or journal entry to be saved.

    ``act_id`` is the recorded act the writing points at; ``resonance_id`` is the resonance it
    marks. Any resonance is valid, in her aura or not, Primal included.
    """

    act_id: int
    resonance_id: int


@dataclass(frozen=True)
class MarkResult:
    """What recording a mark left: the private line its writer reads and the gain it paid.

    ``grant`` is None when nothing paid and the act stays pointable (a pose in an ephemeral
    scene keeps no row to carry the mark); ``line`` then says why and what to do next.
    """

    line: str
    grant: ResonanceGrant | None = None

    @property
    def paid(self) -> bool:
        return self.grant is not None


@dataclass(frozen=True)
class WeeklyStanding:
    """Where a character stands on the weekly table of marks, before the mark in hand.

    ``gained`` is what her marks have paid this game week that nobody undid, ``marks`` how many
    marks that is, and ``percent_paid`` the share of the next mark the table lets through (100
    when no row applies).
    """

    gained: int
    marks: int
    percent_paid: int


@dataclass(frozen=True)
class GainFatigueCharge:
    """What charging a gain's fatigue did to the gain.

    ``amount`` is the gain after any shrinking (0 means nothing can be paid and nothing was
    charged), ``charged`` the fatigue the payer took, and ``payer`` who took it (None when
    nobody did). ``shrunk`` is true when ``amount`` is below what was asked.
    """

    amount: int
    charged: int
    payer: CharacterSheet | None
    shrunk: bool = False

    @property
    def refused(self) -> bool:
        return self.amount <= 0
