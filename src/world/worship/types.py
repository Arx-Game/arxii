"""Typed results for worship services (#4333)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.checks.types import CheckResult, ModifierContribution
    from world.worship.models import DevotionStanding, FavorInvocation, WorshippedBeing


@dataclass(frozen=True)
class DevotionBump:
    """What ``bump_devotion`` wrote: the standing and the favor actually credited.

    ``credited`` is the amount after the earning rate (#4333, design 1a), which a
    caller records and reports in place of the base amount it passed in.
    """

    standing: DevotionStanding
    credited: int


@dataclass(frozen=True)
class InvocationChoice:
    """A Call on favor choice as it arrives from a request or command (#4333):
    the being's pk and the optional line, not yet checked."""

    being_id: int
    player_line: str = ""


@dataclass(frozen=True)
class InvocationRequest:
    """A player's choice to call on ``being`` before a check (#4333): the being
    and the optional one-line description. The invocation itself rolls later,
    when the check it was declared on does."""

    being: WorshippedBeing
    player_line: str = ""


@dataclass(frozen=True)
class InvocationEase:
    """One labelled ease on the invocation check, in difficulty points."""

    label: str
    points: int


@dataclass(frozen=True)
class InvocationDifficulty:
    """How hard an invocation check is for one character and being, and why.

    ``points`` is the final difficulty: ``base_points`` minus every ease, never
    below Trivial. ``band`` is the ``DifficultyChoice`` value nearest to it.
    """

    base_points: int
    base_band: str
    eases: tuple[InvocationEase, ...]
    points: int
    band: str


@dataclass(frozen=True)
class InvocationBonusRow:
    """The bonus one outcome tier gives, for the picker's bonus line."""

    outcome_name: str
    success_level: int
    bonus: int


@dataclass(frozen=True)
class InvocationOption:
    """One being a character could call on, for the Call on favor picker.

    ``refusal`` is the player-facing reason invoking is refused, or "" when the
    character can invoke this being now.
    """

    being: WorshippedBeing
    favor: int
    difficulty: InvocationDifficulty | None
    uses_left: int
    uses_per_week: int
    refusal: str

    @property
    def can_invoke(self) -> bool:
        return not self.refusal


@dataclass(frozen=True)
class InvocationOutcome:
    """One rolled invocation: the row, the roll and the contribution it adds.

    ``contribution`` is the labelled ``ModifierContribution`` (source kind FAVOR)
    for the check the invocation was declared on, or None when the tier gives no
    bonus. ``call_line``/``outcome_line`` are the public strings; for a secret
    faith ``call_line`` names no being and omits the player line, and
    ``private_call_line`` is the acting player's own version.
    """

    invocation: FavorInvocation
    difficulty: InvocationDifficulty
    check_result: CheckResult
    contribution: ModifierContribution | None
    call_line: str
    private_call_line: str
    outcome_line: str

    @property
    def bonus(self) -> int:
        return self.invocation.bonus
