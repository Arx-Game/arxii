"""Core types for the action system."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend, ActionCategory, TargetKind
from world.mechanics.constants import DifficultyIndicator

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.base import Action
    from actions.models import ActionEnhancement
    from actions.models.action_templates import ActionTemplate
    from actions.models.consequence_pools import ConsequencePoolEntry
    from flows.scene_data_manager import SceneDataManager
    from world.checks.models import CheckType, Consequence
    from world.checks.types import CheckResult
    from world.mechanics.types import ChallengeResolutionResult
    from world.scenes.action_availability import AvailableEnhancement
    from world.traits.models import CheckOutcome


class TargetType(StrEnum):
    """What kind of target an action operates on."""

    SELF = "self"
    SINGLE = "single"
    AREA = "area"
    FILTERED_GROUP = "filtered_group"


@dataclass
class ActionResult:
    """Structured result from action execution."""

    success: bool
    message: str | None = None
    broadcast: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class SceneActionResult:
    """Result of a scene-based social action check."""

    success: bool
    action_key: str
    difficulty: int
    message: str | None = None
    interaction_id: int | None = None
    action_request_id: int | None = None
    check_outcome: str | None = None


@dataclass
class ActionContext:
    """Mutable execution context passed to enhancement sources.

    Sources can read and modify anything here. The action's ``execute()``
    decides what to do with the modifications.

    Attributes:
        action: The action being executed.
        actor: The character performing the action.
        target: Optional target of the action.
        kwargs: The action's keyword arguments — enhancements can modify these.
        scene_data: Full scene state access.
        modifiers: Unstructured modifier bag — actions interpret specific keys.
            E.g. a combat action reads ``modifiers["check_bonus"]``.
        post_effects: Callables run after execution, each receiving the context.
        result: Set after execution completes.
    """

    action: Action
    actor: ObjectDB
    target: ObjectDB | None
    kwargs: dict[str, Any]
    scene_data: SceneDataManager

    modifiers: dict[str, Any] = field(default_factory=dict)
    post_effects: list[Callable[[ActionContext], None]] = field(default_factory=list)
    result: ActionResult | None = None


@dataclass
class ActionAvailability:
    """Result of checking whether an action is available."""

    action_key: str
    available: bool
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ActionRef:
    """Typed, round-trippable dispatch reference echoed back by clients.

    This is the ONLY piece serialized over the wire. All identifying ids are
    optional; the relevant one(s) are populated per backend.

    - CHALLENGE: challenge_instance_id + approach_id
    - COMBAT (technique): technique_id
    - COMBAT (clash contribution): clash_id + clash_action_slot
    - REGISTRY: registry_key

    COMBAT ActionRef encoding
    -------------------------
    Two mutually exclusive COMBAT variants:

    1. Technique declaration: ``technique_id`` is set, ``clash_id`` / ``clash_action_slot``
       are ``None``.  Used by the normal round-declaration path.

    2. Clash contribution: ``clash_id`` + ``clash_action_slot`` are both set,
       ``technique_id`` is ``None``.  A future dispatcher reads these two fields to
       route to ``declare_clash_contribution``.  ``clash_action_slot`` is a
       ``ClashActionSlot`` string value (``"FOCUSED"`` or ``"PASSIVE"``).

    Reversibility contract
    ----------------------
    A future dispatch handler can recover ``(clash_id, action_slot)`` from this ref
    via ``ref.clash_id`` and ``ref.clash_action_slot``.  No encoding/decoding step
    needed — the ids are stored as plain ints/strings.
    """

    backend: ActionBackend
    challenge_instance_id: int | None = None
    approach_id: int | None = None
    technique_id: int | None = None
    registry_key: str | None = None
    clash_id: int | None = None
    clash_action_slot: str | None = None

    def __post_init__(self) -> None:
        if self.backend == ActionBackend.CHALLENGE and self.challenge_instance_id is None:
            msg = "CHALLENGE ActionRef requires challenge_instance_id"
            raise ValueError(msg)
        if self.backend == ActionBackend.COMBAT:
            has_technique = self.technique_id is not None
            has_clash = self.clash_id is not None and self.clash_action_slot is not None
            if not has_technique and not has_clash:
                msg = (
                    "COMBAT ActionRef requires either technique_id "
                    "or (clash_id + clash_action_slot)"
                )
                raise ValueError(msg)
            if has_technique and has_clash:
                msg = "COMBAT ActionRef must not set both technique_id and clash_id"
                raise ValueError(msg)
        if self.backend == ActionBackend.REGISTRY and self.registry_key is None:
            msg = "REGISTRY ActionRef requires registry_key"
            raise ValueError(msg)


@dataclass
class DispatchResult:
    """Result of a ``dispatch_player_action`` call.

    ``deferred`` is True when the action was recorded as a round declaration
    (waiting for ``resolve_round`` to resolve it) rather than executed immediately.
    ``backend`` identifies which pipeline handled the dispatch.
    ``detail`` carries the immediate result object when ``deferred`` is False:
    - CHALLENGE → ``ChallengeResolutionResult``
    - REGISTRY  → ``ActionResult``
    - COMBAT (deferred) → None (deferred; resolved later by resolve_round)
    - CHALLENGE (deferred) → None (deferred; resolved later by resolve_round)
    """

    backend: ActionBackend
    deferred: bool
    detail: ChallengeResolutionResult | ActionResult | None = None


@dataclass
class PlayerAction:
    """Homogeneous descriptor for a single player-actionable action.

    Emitted by the merged availability service across challenge/combat/registry
    backends. Carries model instances (not bare PKs) per project convention;
    only ActionRef holds primitive ids for wire serialization.

    ``check_type`` is present for most actions — it is the unifying resolution
    anchor resolved per-backend before this descriptor is constructed.  For
    clash-contribution actions, ``check_type`` is ``None`` because the check
    type is determined by the technique the PC selects at declaration time, not
    at opportunity-surfacing time.

    ``action_template`` is optional: present for combat techniques, registry
    templates, and override challenge approaches; None for plain
    check_type-direct challenge approaches and clash contributions.

    When ``action_template`` is present, ``PlayerAction.check_type`` remains
    authoritative; ``action_template.check_type`` may differ for override approaches.
    """

    # --- required fields (no defaults) ---
    backend: ActionBackend
    display_name: str
    ref: ActionRef

    # --- optional fields (with defaults) ---
    # None for clash contributions: technique chosen at declaration time determines the check.
    check_type: CheckType | None = None
    action_template: ActionTemplate | None = None
    description: str = ""
    difficulty: DifficultyIndicator | None = None
    prerequisite_met: bool = True
    prerequisite_reasons: list[str] = field(default_factory=list)

    # Targeting / enhancement / strain descriptors for the frontend.
    # ``target_spec=None`` means a self-action; otherwise it describes the
    # entity-type axis plus cardinality and filters. ``enhancements`` reuses
    # the existing ``AvailableEnhancement`` shape from scenes/action_availability.
    # ``strain`` carries the per-character cap snapshot when applicable.
    target_spec: TargetSpec | None = None
    enhancements: tuple[AvailableEnhancement, ...] = ()
    strain: StrainAvailability | None = None

    # Physical/social/mental arena (set from the technique for combat actions;
    # None when no backend supplies one yet — non-magical actions classify later).
    action_category: ActionCategory | None = None


class ActionInterrupted(Exception):
    """Raised when a trigger stops an action's intent event."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class EnhancementSource:
    """Mixin for models that can be ActionEnhancement sources.

    Source models (techniques, distinctions, conditions) inherit this mixin
    to participate in the enhancement system. Sources only answer one question:
    "does this actor have me right now?" The *effect* of the enhancement lives
    on the ``ActionEnhancement`` record's ``effect_parameters``, not here.

    Example::

        class Distinction(EnhancementSource, SharedMemoryModel):
            name = models.CharField(max_length=100)

            def should_apply_enhancement(self, actor, enhancement):
                return CharacterDistinction.objects.filter(
                    character=actor, distinction=self,
                ).exists()
    """

    def should_apply_enhancement(
        self,
        actor: ObjectDB,
        enhancement: ActionEnhancement,
    ) -> bool:
        """Return True if this source's enhancement applies to actor right now.

        Called for involuntary enhancements to filter which ones activate.
        Voluntary enhancements skip this check — the player chose them.
        """
        raise NotImplementedError


@dataclass
class WeightedConsequence:
    """A Consequence with its effective weight for a specific pool.

    Uses 'weight' attribute name so select_weighted() and filter_character_loss()
    can read it via getattr(item, "weight").
    """

    consequence: Consequence
    weight: int
    character_loss: bool  # forwarded from consequence for filter_character_loss()

    @property
    def outcome_tier(self) -> CheckOutcome:
        return self.consequence.outcome_tier

    @property
    def label(self) -> str:
        return self.consequence.label

    @property
    def pk(self) -> int | None:
        return self.consequence.pk


def _entry_to_weighted(entry: ConsequencePoolEntry) -> WeightedConsequence:
    """Convert a single ConsequencePoolEntry to a WeightedConsequence.

    Uses weight_override when set; falls back to the consequence's own weight.
    """
    consequence = entry.consequence
    weight_override = entry.weight_override
    return WeightedConsequence(
        consequence=consequence,
        weight=weight_override if weight_override is not None else consequence.weight,
        character_loss=consequence.character_loss,
    )


@dataclass
class StepResult:
    """Outcome of a single resolution step."""

    step_label: str
    check_result: CheckResult
    consequence_id: int | None  # PK of selected Consequence (None for no-op)
    applied_effect_ids: list[int] | None = None  # PKs of created instances, None until applied
    was_rerolled: bool = False


@dataclass
class PendingActionResolution:
    """State of an in-progress action template resolution."""

    template_id: int
    character_id: int
    target_difficulty: int
    resolution_context_data: dict[str, int | None]

    current_phase: str  # ResolutionPhase value
    gate_results: list[StepResult] = field(default_factory=list)
    main_result: StepResult | None = None
    context_results: list[StepResult] = field(default_factory=list)

    awaiting_confirmation: bool = False
    awaiting_intervention: bool = False
    intervention_options: list[str] = field(default_factory=list)
    # Roller-side check bonus (effort + specialization etc.), carried so the
    # resume path can re-apply it after a confirmation pause.
    extra_modifiers: int = 0


@dataclass(frozen=True)
class TargetFilters:
    """Boolean filter flags applied client-side to candidate targets."""

    in_same_scene: bool = False
    in_same_zone: bool = False
    exclude_self: bool = False
    must_be_conscious: bool = False


@dataclass(frozen=True)
class TargetSpec:
    """Describes what a targeted action accepts as its target.

    ``cardinality`` is the existing ``TargetType`` enum (SINGLE / AREA /
    FILTERED_GROUP); self-actions have ``target_spec=None`` on
    ``PlayerAction`` rather than ``cardinality=SELF``.
    """

    kind: TargetKind
    cardinality: TargetType
    filters: TargetFilters


@dataclass(frozen=True)
class StrainAvailability:
    """Per-character strain cap snapshot for a single GET of available actions."""

    cap: int
    default: int = 0
