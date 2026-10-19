"""Typed results for worship services (#4333)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.worship.constants import PledgeCreditSource

if TYPE_CHECKING:
    from datetime import datetime

    from world.ceremonies.models import CeremonyOffering
    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult, ModifierContribution
    from world.magic.models import ResonanceGrant
    from world.traits.models import CheckOutcome
    from world.worship.models import (
        Answer,
        DevotionStanding,
        FavorInvocation,
        Miracle,
        MiraclePerformance,
        PledgeCredit,
        PledgeDetails,
        Vision,
        WorshippedBeing,
        WorshipRite,
        WorshipRitePerformance,
    )


@dataclass(frozen=True)
class DevotionBump:
    """What ``bump_devotion`` wrote: the standing and the favor actually credited.

    ``credited`` is the amount after the earning rate (#4333, design 1a), which a
    caller records and reports in place of the base amount it passed in.
    """

    standing: DevotionStanding
    credited: int
    pledge_credit: PledgeCredit | None = None
    earning_rate_percent: int = 100


@dataclass(frozen=True)
class FavorSource:
    """What a favor write is for, so an open pledge can record it (#4333 slice 2).

    Passed to ``bump_devotion``; ``kind`` is a ``PledgeCreditSource`` and the
    typed rows name the deed's resonance grant, the sacrifice's offering or the
    rite's performance. ``pledge_details`` names the pledge outright, for the
    closing and lapse awards paid while it resolves; otherwise the character's
    open pledge to the being is used.
    """

    kind: str = PledgeCreditSource.OTHER
    resonance_grant: ResonanceGrant | None = None
    offering: CeremonyOffering | None = None
    rite_performance: WorshipRitePerformance | None = None
    pledge_details: PledgeDetails | None = None


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
class InvocationPicker:
    """The Call on favor picker's data for one character (#4333)."""

    beings: list[InvocationOption]
    bonuses: tuple[InvocationBonusRow, ...]


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


@dataclass(frozen=True)
class EarningRateBreakdown:
    """A character's earning rate with one being, in its parts (#4333, design 1a)."""

    base: int
    chosen_bonus: int
    modifiers: int

    @property
    def total(self) -> int:
        return max(self.base + self.chosen_bonus + self.modifiers, 0)


@dataclass(frozen=True)
class ServiceTermLine:
    """One system-generated line of what earns favor with a being, and how much."""

    label: str
    amount: str


@dataclass(frozen=True)
class ServiceTerms:
    """What earns favor with ``being`` for one character (#4333 slice 2): the
    pledge dialog's and the pledge card's system-generated list."""

    being: WorshippedBeing
    rate: EarningRateBreakdown
    lines: list[ServiceTermLine]
    weekly_deed_cap: int


@dataclass(frozen=True)
class PledgeCreditLine:
    """One credit on the pledge card, with its calculation in words."""

    id: int  # the PledgeCredit row, a stable key for the card's list
    source: str
    label: str
    calculation: str
    credited: int
    counts_toward_progress: bool
    created_at: datetime


@dataclass(frozen=True)
class PledgeCard:
    """A character's pledge as the card shows it (#4333 slice 2)."""

    details: PledgeDetails
    state: str
    progress: int
    target: int
    time_limit: datetime
    close_attempts: int
    retry_available: bool
    favor: int
    credits: list[PledgeCreditLine]
    terms: ServiceTerms


@dataclass(frozen=True)
class ClosingOutcome:
    """What one closing rite did (#4333 slice 2, Ruling 17).

    ``resolved`` is False after a first Failure or Critical Failure, which
    leaves one retry; then nothing is paid. Otherwise the pledge resolved and
    ``award`` is the closing award credited (``award_base`` before the rate).
    """

    details: PledgeDetails
    rite: WorshipRite
    outcome_name: str
    resolved: bool
    award_base: int
    award: int
    earning_rate_percent: int
    delivery: AnswerDelivery | None = None


@dataclass(frozen=True)
class AnswerDelivery:
    """What a resolved pledge's answer came to (#4333 slice 3).

    ``answer`` is None when the being had no answer that fit the draw (no
    vision), or when its steward wrote the vision's text. ``held`` is True when
    the being's worship pool could not pay and a ``PendingAnswer`` holds it;
    ``vision`` is the delivered vision otherwise. ``awaiting_steward`` is True
    when the closing went to a stewarded being's table GM as a ``BEING_ANSWER``
    prompt (slice 4): nothing is drawn or sent yet.
    """

    answer: Answer | None
    vision: Vision | None
    held: bool
    awaiting_steward: bool = False


@dataclass(frozen=True)
class SacrificedItem:
    """One item given up at a shrine or temple, and the favor it earned."""

    name: str
    credited: int
    calculation: str


@dataclass(frozen=True)
class SacrificeOutcome:
    """A sacrifice (#4333 slice 2): to whom, at which kind of site, and each item."""

    being: WorshippedBeing
    site: str
    items: list[SacrificedItem]


@dataclass(frozen=True)
class HolySite:
    """A being holy where a character stands: its shrine in the room ("shrine") or
    the temple over it ("temple")."""

    being: WorshippedBeing
    site: str

    @property
    def being_id(self) -> int:
        return self.being.pk

    @property
    def being_name(self) -> str:
        return self.being.name


@dataclass(frozen=True)
class LiveAnswerOption:
    """One authored answer on the live panel: the row and how often it has been sent."""

    answer: Answer
    used_count: int


@dataclass(frozen=True)
class LiveMiracleOption:
    """One miracle on the live panel; a non-empty ``reason`` greys it out."""

    miracle: Miracle
    reason: str


@dataclass(frozen=True)
class LivePanel:
    """What a GM sees when a rite in their scene asks them to answer it (#4333 slice 5).

    ``limit_reason`` is non-empty when the being already answered this character
    live this game week: the panel then lists what exists but nothing can be sent.
    ``may_adapt`` is the viewing GM's level: the answer's main text is editable only
    when true.
    """

    being: WorshippedBeing
    sheet: CharacterSheet
    rite: WorshipRite
    tier: CheckOutcome
    answers: list[LiveAnswerOption]
    miracles: list[LiveMiracleOption]
    may_adapt: bool
    limit_reason: str


@dataclass(frozen=True)
class LiveSend:
    """What a live send delivered: a vision (an answer) or a miracle performance."""

    being: WorshippedBeing
    sheet: CharacterSheet
    answer: Answer | None = None
    vision: Vision | None = None
    miracle: Miracle | None = None
    performance: MiraclePerformance | None = None
