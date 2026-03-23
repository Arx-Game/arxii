"""Core types for the action system."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.base import Action
    from actions.models import ActionEnhancement
    from flows.scene_data_manager import SceneDataManager
    from world.checks.models import Consequence
    from world.checks.types import CheckResult
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
