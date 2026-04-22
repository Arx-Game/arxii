from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter, CombatParticipant
    from world.conditions.models import CapabilityType
    from world.magic.models import Thread


@dataclass(frozen=True)
class PullActionContext:
    """Context describing the action the pull would attach to (Spec A §5.4).

    Combat-context pulls supply both ``combat_encounter`` and ``participant``;
    ephemeral (RP) pulls leave both ``None``. The ``involved_*`` tuples carry
    the typed-FK pks that describe which anchors the action engages, so
    ``_anchor_in_action`` can avoid introspecting the action graph from inside
    the service layer (caller is responsible for populating them).

    Distinct from ``actions.types.ActionContext`` — that dataclass is the
    generic action-resolver context with totally different fields.
    """

    combat_encounter: CombatEncounter | None = None
    participant: CombatParticipant | None = None
    involved_traits: tuple[int, ...] = ()
    involved_techniques: tuple[int, ...] = ()
    involved_objects: tuple[int, ...] = ()


@dataclass(frozen=True)
class ResolvedPullEffect:
    """One resolved pull effect (per-thread × per-tier; Spec A §5.4 step 3).

    ``inactive`` flags VITAL_BONUS rows in ephemeral context — the cost is
    still paid in full but ``scaled_value`` is zeroed since there is no
    combat consumer for the bonus. ``inactive_reason`` carries the player-
    facing explanation.
    """

    kind: str
    authored_value: int | None
    level_multiplier: int
    scaled_value: int
    vital_target: str | None
    source_thread: Thread
    source_thread_level: int
    source_tier: int
    granted_capability: CapabilityType | None
    narrative_snippet: str
    inactive: bool = False
    inactive_reason: str | None = None


@dataclass(frozen=True)
class ResonancePullResult:
    """Result of ``spend_resonance_for_pull`` (Spec A §5.4 step 8)."""

    resonance_spent: int
    anima_spent: int
    resolved_effects: list[ResolvedPullEffect]


@dataclass(frozen=True)
class PullPreviewResult:
    """Read-only preview of a resonance pull (Spec A §5.6).

    Returned by ``preview_resonance_pull`` for the pre-commit UI. Contains
    everything the client needs to render the pull panel without mutating
    any state. ``capped_intensity`` is True when the summed INTENSITY_BUMP
    across ``resolved_effects`` would exceed the highest authored
    IntensityTier threshold.
    """

    resonance_cost: int
    anima_cost: int
    affordable: bool
    resolved_effects: list[ResolvedPullEffect]
    capped_intensity: bool
