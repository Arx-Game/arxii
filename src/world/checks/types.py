"""Type definitions for the check system."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from world.checks.constants import ModifierSourceKind

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.assets.models import NPCAsset
    from world.checks.models import CheckType, Consequence
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
    """

    source_kind: str
    source_label: str
    value: int
    condition_instance_id: int | None = None


@dataclass
class ModifierBreakdown:
    """Aggregated modifier provenance for a check.

    ``total`` is the full recorded shift (what provenance and ``ConsequenceOutcome``
    store). ``extra_modifiers_total`` is the part a caller adds into
    ``perform_check``'s ``extra_modifiers``: it leaves out CAPABILITY contributions,
    because the roll path (``_compute_check_breakdown``) already adds the same points
    itself. Feeding ``total`` into ``extra_modifiers`` counts capability twice (#4453).
    """

    contributions: list[ModifierContribution] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(c.value for c in self.contributions)

    @property
    def extra_modifiers_total(self) -> int:
        return sum(
            c.value for c in self.contributions if c.source_kind != ModifierSourceKind.CAPABILITY
        )


@dataclass
class PendingResolution:
    """Intermediate result for the two-step consequence pipeline."""

    check_result: CheckResult
    selected_consequence: Consequence
