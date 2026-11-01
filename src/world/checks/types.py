"""Type definitions for the check system."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, cast

from world.checks.constants import ROLL_COUNTED_SOURCE_KINDS

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.assets.models import NPCAsset
    from world.checks.models import CheckType, Consequence
    from world.checks.slide import CheckStanding
    from world.mechanics.models import ChallengeApproach, ChallengeInstance
    from world.missions.models import MissionInstance
    from world.scenes.models import Interaction, Persona, Scene
    from world.stories.models import Beat, Story
    from world.traits.models import CheckOutcome, CheckRank, ResultChart, Trait


@dataclass(frozen=True)
class ExtraTraitTerm:
    """A trait a caller adds to one roll, on top of the check type's own traits.

    The engine treats it like an extra ``CheckTypeTrait`` row: the character's value in
    ``trait`` times ``weight`` is converted to points, the trait earns check-based
    development when the roll has an effort level, and the trait counts as involved in the
    check for capability thread pulls. Lets a system (magic, for one) put a skill into a
    check without authoring a ``CheckTypeTrait`` row for every combination.
    """

    trait: Trait
    weight: Decimal


@dataclass
class OutcomeDisplay:
    """Single outcome for frontend roulette display. Used by any check-based system."""

    label: str
    tier_name: str
    weight: int
    is_selected: bool


@dataclass
class CheckResult:
    """Result from a check resolution.

    ``effective_roll`` (the clamped d100 after rollmod) is carried for
    server-side magnitude seams — crafting's quality-luck term (#2886) reads
    it so the SAME roll that picked the outcome band also sets how far above
    or below par the result lands. It is never player-serialized; 0 means
    "no roll happened" (forced test outcomes, defaulted duck-types) and
    contributes no luck.

    ``standing`` (#4601) holds both sides' band positions and the slid chart the roll
    used. ``rank_difference`` is that chart's whole difference. None on hand-built
    results (missions, test doubles).
    """

    check_type: CheckType
    outcome: CheckOutcome | None
    chart: ResultChart | None
    roller_rank: CheckRank | None
    target_rank: CheckRank | None
    rank_difference: int
    trait_points: int
    aspect_bonus: int
    total_points: int
    specialization_points: int = 0  # #1688 — points from owned specializations (stat+skill+spec)
    capability_points: int = 0  # #2505 — weighted authored CheckTypeCapabilityModifier points
    level_points: int = 0  # #2707 — LEVEL_POINTS_PER_LEVEL x class level, on every check
    effective_roll: int = 0  # #2886 — the clamped d100; 0 = no roll (forced/duck-typed)
    standing: CheckStanding | None = None  # #4601: band positions and the slide

    def with_outcome(self, outcome: CheckOutcome | None) -> CheckResult:
        """Copy the result while replacing only its outcome tier."""
        return cast(CheckResult, replace(self, outcome=outcome))

    @property
    def rank_text(self) -> str:
        """The roller's rank with its band position, for example "Expert (rank 3), 67%
        toward Master (rank 4)". Falls back to the bare rank on hand-built results."""
        if self.standing is not None:
            return self.standing.roller.text
        if self.roller_rank is not None:
            return f"{self.roller_rank.name} (rank {self.roller_rank.rank})"
        return ""

    @property
    def target_rank_text(self) -> str:
        """The target's rank with its number and band position (#4601)."""
        if self.standing is not None:
            return self.standing.target.text
        if self.target_rank is not None:
            return f"{self.target_rank.name} (rank {self.target_rank.rank})"
        return ""

    @property
    def standing_text(self) -> str:
        """Roller against target, each with rank number and band position (#4601)."""
        if self.standing is not None:
            return self.standing.summary
        return self.rank_text

    @property
    def outcome_name(self) -> str:
        return str(self.outcome.name) if self.outcome else "Unknown"

    @property
    def success_level(self) -> int:
        return int(self.outcome.success_level) if self.outcome else 0

    @property
    def chart_name(self) -> str:
        return str(self.chart.name) if self.chart else "No Chart Found"


@dataclass
class ResolutionContext:
    """Carries character and typed optional source refs for consequence resolution."""

    character: ObjectDB
    challenge_instance: ChallengeInstance | None = None
    action_context: ActionContext | None = None
    target: ObjectDB | None = None
    source_character: ObjectDB | None = None
    participants: list[Persona] | None = None
    beat: Beat | None = None
    scene: Scene | None = None
    story: Story | None = None
    # The run being resolved, when a mission route fires the consequence — lets
    # mission-aware effects reach run state (e.g. a rescue route freeing the
    # run's ``rescue_target``). None outside the mission-resolution path.
    mission_instance: MissionInstance | None = None
    # The already-resolved graded outcome tier, when the consequence pool is being
    # applied against a known tier rather than a freshly-rolled check (beat auto-wire,
    # mission routes). None when the caller rolls its own check via select_consequence().
    outcome_tier: CheckOutcome | None = None
    # The mission-challenge approach the player declared (#1824) — how they chose
    # to do the thing. Effects read it for act-shape: a Stealth approach makes a
    # LEGEND_AWARD deed concealed (the "do it sneakily" declaration surface).
    chosen_approach: ChallengeApproach | None = None
    # The specific dispatched agent at stake (#2820 tasking). When set,
    # ASSET_STATUS effects transition THIS asset only, not every active asset
    # the resolved target character promotes. None on scene/stake paths.
    npc_asset: NPCAsset | None = None
    # The Interaction the resolving act was recorded against, when the caller
    # already created one before firing this context's consequence pool
    # (#2987, e.g. combat's per-round OUTCOME interaction). LEGEND_AWARD reads
    # this to open a WITNESS reaction window on a public, crime-tagged deed.
    # None when no interaction exists yet at resolution time (e.g. the
    # beat-completion path, whose ResolutionContext also carries scene=None).
    interaction: Interaction | None = None

    @property
    def location(self) -> ObjectDB:
        return self.character.location

    @property
    def display_label(self) -> str:
        if self.challenge_instance is not None:
            return self.challenge_instance.template.name
        if self.action_context is not None:
            return str(self.action_context.action)
        msg = "ResolutionContext has no populated source (challenge_instance or action_context)"
        raise ValueError(msg)


@dataclass(frozen=True)
class ModifierContribution:
    """A single modifier with its provenance label and numeric value.

    ``condition_instance_id`` names the ConditionInstance a CONDITION contribution came
    from, so a real roll can spend a once-only (UNTIL_USED) condition that helped it
    (``spend_contributing_conditions``, #4584). None for every other source kind.

    ``level`` and ``size`` (#4594) are the level the modifier counts at and its
    ``ModifierSize``, when its source is sized; ``value`` is then the value table's
    number for that pair, never anything read off the target. An unsized source leaves
    both None and keeps its flat value. ``vow_part`` is the share of ``value`` the
    character's vow supplies; it is never tapered. Today that is the equipment walk's
    covenant role, covenant level and vow stat scaling terms (#4628), and a vowed
    caster's size step on a condition buff or debuff (#4747, signed like the buff).
    """

    source_kind: str
    source_label: str
    value: int
    condition_instance_id: int | None = None
    level: int | None = None
    size: int | None = None
    vow_part: int = 0


@dataclass(frozen=True)
class TaperRule:
    """How one source kind tapers in a lane (a ``ModifierTaper`` row, #4594).

    In a pile, the k-th largest modifier counts ``max(ratio ** (k - 1), floor)`` of its
    taperable value.
    """

    ratio: Decimal
    floor: Decimal

    def weight(self, position: int) -> Decimal:
        """The share the modifier at 0-based ``position`` in its pile counts for."""
        return max(self.ratio**position, self.floor)


@dataclass(frozen=True)
class CountedContribution:
    """A contribution beside what it actually counts for after the taper (#4594)."""

    contribution: ModifierContribution
    counted: Decimal


def round_half_up(value: Decimal) -> int:
    """``value`` to a whole number, halves away from zero (so -1.5 is -2, signed alike)."""
    return int(value.to_integral_value(rounding=ROUND_HALF_UP))


@dataclass
class ModifierBreakdown:
    """Aggregated modifier provenance for a check.

    ``total`` is the full recorded shift (what provenance and ``ConsequenceOutcome``
    store). ``extra_modifiers_total`` is the part a caller adds into
    ``perform_check``'s ``extra_modifiers``: it leaves out the kinds in
    ``ROLL_COUNTED_SOURCE_KINDS``, because ``perform_check`` already counts them itself.
    Feeding ``total`` into ``extra_modifiers`` counts those twice (#4453).

    ``tapers`` (#4594) maps a source kind to its ``TaperRule``. The contributions of a
    tapered kind form two piles, bonuses and penalties; each pile counts largest first,
    the k-th at ``rule.weight(k - 1)`` of its value less its untapered ``vow_part``. A
    kind with no rule (the character's own standing: rollmod, effort, fatigue, strain,
    soulfray, capability) adds at face value. An empty mapping is a plain sum. Both
    totals round once, half up, after the piles are summed.
    """

    contributions: list[ModifierContribution] = field(default_factory=list)
    tapers: dict[str, TaperRule] = field(default_factory=dict)

    def counted(self) -> list[CountedContribution]:
        """Every contribution with what it counts for, in the original order."""
        counted: dict[int, Decimal] = {}
        piles: dict[tuple[str, bool], list[int]] = {}
        for index, contribution in enumerate(self.contributions):
            if contribution.source_kind in self.tapers:
                taperable = contribution.value - contribution.vow_part
                piles.setdefault((contribution.source_kind, taperable >= 0), []).append(index)
            else:
                counted[index] = Decimal(contribution.value)
        for (kind, _is_bonus), indexes in piles.items():
            rule = self.tapers[kind]
            ordered = sorted(
                indexes,
                key=lambda i: -abs(self.contributions[i].value - self.contributions[i].vow_part),
            )
            for position, index in enumerate(ordered):
                contribution = self.contributions[index]
                taperable = contribution.value - contribution.vow_part
                counted[index] = contribution.vow_part + taperable * rule.weight(position)
        return [
            CountedContribution(contribution=contribution, counted=counted[index])
            for index, contribution in enumerate(self.contributions)
        ]

    def counted_values(self) -> list[int]:
        """What each contribution counts for, as whole numbers summing exactly to ``total``.

        Each counted share is floored toward zero and the leftover units go to the largest
        remainders, so recorded provenance rows (``ConsequenceOutcomeModifier``) add up to the
        tapered total the roll used. Untapered contributions keep their exact value.
        """
        counted = [c.counted for c in self.counted()]
        floored = [int(value) for value in counted]  # int() truncates toward zero
        leftover = self.total - sum(floored)
        step = 1 if leftover > 0 else -1
        order = sorted(
            range(len(counted)),
            key=lambda i: (counted[i] - floored[i]) * step,
            reverse=True,
        )
        for index in order[: abs(leftover)]:
            floored[index] += step
        return floored

    @property
    def total(self) -> int:
        return round_half_up(sum((c.counted for c in self.counted()), Decimal(0)))

    @property
    def extra_modifiers_total(self) -> int:
        return round_half_up(
            sum(
                (
                    c.counted
                    for c in self.counted()
                    if c.contribution.source_kind not in ROLL_COUNTED_SOURCE_KINDS
                ),
                Decimal(0),
            )
        )


@dataclass
class PendingResolution:
    """Intermediate result for the two-step consequence pipeline."""

    check_result: CheckResult
    selected_consequence: Consequence


@dataclass(frozen=True)
class RollLine:
    """One source in a roll's breakdown as a player reads it (#4858): what it is, its
    number when it has one, and why it counts."""

    label: str
    value: str
    detail: str
    # The source would have counted and did not (#4884): a lapsed style skill, drawn
    # struck through.
    lapsed: bool = False


@dataclass(frozen=True)
class RollBreakdown:
    """A recorded roll laid out as rows (#4858): a heading, one line per source, and the
    result line. Built at read time for a roll whose system knows its sources (a Strike)."""

    heading: str
    lines: list[RollLine] = field(default_factory=list)
    result: str = ""
    # A note beside the result line ("then the damage roll" on a hit that went on).
    result_note: str = ""


@dataclass(frozen=True)
class RollSnapshot:
    """What a recorded roll's breakdown names, captured when the roll is made (#4858)."""

    weapon_label: str
    weapon_kind: str
    stat_label: str
    # The attacker's combat style on the roll (#4884): its name, the style skill rating
    # when it counted, why it lapsed when it did not, and whether the stat is the style's
    # hit stat. Empty name: no style term.
    style_name: str = ""
    style_skill_rating: int | None = None
    style_lapse_note: str = ""
    stat_from_style: bool = False
