"""
Mechanics System Types

Dataclasses and type definitions for the mechanics service layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models.action_templates import ActionTemplate
    from world.checks.models import CheckType, Consequence
    from world.checks.types import CheckResult
    from world.mechanics.models import ChallengeApproach, ChallengeInstance, ChallengeTemplate

from world.checks.types import OutcomeDisplay
from world.mechanics.constants import CapabilitySourceType, DifficultyIndicator
from world.mechanics.models import Prerequisite

# Re-export for backwards compatibility within mechanics app
ConsequenceDisplay = OutcomeDisplay

if TYPE_CHECKING:
    from world.conditions.models import CapabilityType
    from world.mechanics.models import Property


class HasCapabilities(Protocol):
    """Duck-typed contract: something that can be asked for its magnitude on a
    CapabilityType. Implemented by CharacterSheet (delegates to
    get_effective_capability_value) and BattleUnit (reads its own
    BattleUnitCapability rows) — no isinstance branching (#1794)."""

    def effective_capability(self, capability: CapabilityType) -> int: ...


class HasProperties(Protocol):
    """Duck-typed contract: something that can be asked whether it carries a
    Property tag. Implemented by CharacterSheet (delegates to ObjectProperty/
    persona-authored properties) and BattleUnit (reads its own properties M2M)
    — no isinstance branching (#1794)."""

    def has_property(self, prop: Property) -> bool: ...


@dataclass
class ModifierSourceDetail:
    """Single modifier source with calculation details.

    ``level`` and ``size`` (#4638) are set only when a sized distinction effect was valued
    from a lane's value table (``get_modifier_breakdown(value_lane=...)``): the holder's
    level and the ``ModifierSize`` the held rank names (#4660: rank steps the size, never
    multiplies the number). ``base_value`` is then the table's number. Every other source
    leaves both None and keeps its flat value.
    """

    source_name: str
    base_value: int
    amplification: int
    final_value: int
    is_amplifier: bool
    blocked_by_immunity: bool
    level: int | None = None
    size: int | None = None


@dataclass
class ModifierBreakdown:
    """Full breakdown for a modifier target."""

    modifier_target_name: str
    sources: list[ModifierSourceDetail]
    total: int
    has_immunity: bool
    negatives_blocked: int


@dataclass
class PrerequisiteEvaluation:
    """Result of evaluating a Prerequisite against game state."""

    met: bool
    reason: str = ""


@dataclass
class CapabilitySource:
    """A single source of a Capability for a character."""

    capability_name: str
    capability_id: int
    value: int
    source_type: CapabilitySourceType
    source_name: str  # e.g., "Flame Lance", "Strength"
    source_id: int
    effect_property_ids: list[int] = field(default_factory=list)
    prerequisite: Prerequisite | None = None


@dataclass
class AvailableAction:
    """An Action available to a character for a specific Challenge.

    ``resolved_check_type`` and ``resolved_action_template`` carry the already-loaded
    model instances (populated from the prefetched ChallengeApproach by
    ``_match_approaches``).  They are excluded from wire serialization because
    DataclassSerializer cannot render arbitrary model instances — the unified
    ``get_player_actions`` adapter in ``actions.player_interface`` reads them
    directly to build ``PlayerAction`` descriptors.  ``check_type_name`` is kept
    as the wire-safe string representation for any consumer that reads the dataclass
    without going through the unified adapter.

    Bare-object affordances (#2503): when an ``Application`` with a
    ``default_template`` matches an ``ObjectProperty`` on an object at the
    location (rather than an authored, already-placed ``ChallengeInstance``),
    ``challenge_instance_id``/``resolved_challenge_instance`` are ``None`` —
    no instance exists yet — and ``target_object``/``resolved_default_template``
    carry what dispatch needs to mint one: ``instantiate_challenge(
    resolved_default_template, location, target_object)``. ``resolved_challenge_approach``
    is still populated (the default template's own matching approach), so
    check_type/consequences resolve identically whether or not an instance
    exists yet.
    """

    application_id: int
    application_name: str
    capability_source: CapabilitySource
    challenge_instance_id: int | None
    challenge_name: str
    approach_id: int | None
    check_type_name: str
    display_name: str
    custom_description: str
    difficulty_indicator: DifficultyIndicator | None = None
    prerequisite_met: bool = True
    prerequisite_reasons: list[str] = field(default_factory=list)
    # Resolved model instances (populated from already-prefetched approach data).
    # Default None so existing construction sites that don't pass these still work.
    resolved_check_type: CheckType | None = field(default=None)
    resolved_action_template: ActionTemplate | None = field(default=None)
    # Challenge/approach instances for dispatch — populated from already-loaded prefetch
    # data in _match_approaches (no additional query).  Excluded from wire serialization.
    resolved_challenge_instance: ChallengeInstance | None = field(default=None)
    resolved_challenge_approach: ChallengeApproach | None = field(default=None)
    # Bare-object affordance fields (#2503) — populated instead of
    # resolved_challenge_instance when the action is synthesized from an
    # ObjectProperty match rather than an authored ChallengeInstance.
    target_object: ObjectDB | None = field(default=None)  # noqa: OBJECTDB_PARAM
    resolved_default_template: ChallengeTemplate | None = field(default=None)


@dataclass
class ChallengeGroup:
    """Available actions grouped by challenge for API response."""

    challenge_instance_id: int
    challenge_name: str
    actions: list[AvailableAction]


class ChallengeResolutionError(Exception):
    """Raised when challenge resolution is called with invalid state."""


@dataclass
class AppliedEffect:
    """Record of a single effect that was applied or skipped."""

    effect_type: str
    description: str
    applied: bool
    skip_reason: str = ""
    created_instance: Any | None = None  # optional ref for caller bookkeeping


@dataclass
class ChallengeResolutionResult:
    """Full result from resolve_challenge()."""

    challenge_instance_id: int
    challenge_name: str
    approach_name: str
    check_result: CheckResult
    consequence: Consequence
    applied_effects: list[AppliedEffect]
    resolution_type: str
    challenge_deactivated: bool
    display_consequences: list[OutcomeDisplay]


@dataclass(frozen=True)
class EquipmentWalkParts:
    """The equipment walk split by who supplies it (#4628).

    ``item_part`` is what the worn pieces carry through the character's threads (facet,
    facet crossing, mantle, mantle crossing and motif style passives): a worn-item
    modifier that tapers with the EQUIPMENT pile. ``vow_part`` is the covenant role,
    covenant level and vow stat scaling bonuses: the character's vow, never tapered
    (#4551 decision 1).
    """

    item_part: int = 0
    vow_part: int = 0

    @property
    def total(self) -> int:
        return self.item_part + self.vow_part


@dataclass(frozen=True)
class TechniqueEffectContext:
    """What a cast technique is, as a technique-scoped modifier target sees it (#4822).

    ``gift_ids`` holds the technique's gift and that gift's parent (the umbrella gift),
    so a target scoped to the umbrella reaches every child gift's techniques.
    ``functions`` holds ``TechniqueFunction`` values, ``resonance_ids`` the resonances
    the gift manifests as for this caster, and ``damage_type_id`` the resolved damage
    type (damage effects only). ``opponent_property_ids`` and ``opponent_condition_ids``
    (#4823) are who the effect lands on: the properties and the active conditions the
    opponent carries, read only when an opponent-scoped target is in the game.
    """

    technique_id: int
    gift_ids: frozenset[int]
    functions: frozenset[str]
    resonance_ids: frozenset[int]
    damage_type_id: int | None = None
    opponent_property_ids: frozenset[int] = frozenset()
    opponent_condition_ids: frozenset[int] = frozenset()

    def landing_on(
        self, facts: OpponentFacts, damage_type_id: int | None = None
    ) -> TechniqueEffectContext:
        """This cast as it lands on an opponent carrying ``facts`` (#4823), with the hit's
        resolved ``damage_type_id`` for damage (a condition's context has none)."""
        return TechniqueEffectContext(
            technique_id=self.technique_id,
            gift_ids=self.gift_ids,
            functions=self.functions,
            resonance_ids=self.resonance_ids,
            damage_type_id=damage_type_id,
            opponent_property_ids=facts.property_ids,
            opponent_condition_ids=facts.condition_ids,
        )


@dataclass(frozen=True)
class OpponentFacts:
    """What an opponent carries, as an opponent-scoped modifier target sees it (#4823).

    ``property_ids`` is every property the opponent has by any of the game's three routes
    (a stored ``ObjectProperty``, a property an active condition's template or current stage
    grants, a persona-authored tag); ``condition_ids`` the templates of its active,
    unsuppressed conditions.
    """

    property_ids: frozenset[int] = frozenset()
    condition_ids: frozenset[int] = frozenset()
