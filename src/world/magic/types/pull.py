from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.combat.models import CombatEncounter, CombatParticipant
    from world.conditions.models import CapabilityType, DamageType
    from world.forms.models import CharacterForm
    from world.magic.models import Resonance, Thread


@dataclass(frozen=True)
class PullActionContext:
    """Context describing the action the pull would attach to (Spec A §5.4).

    Combat-context pulls supply both ``combat_encounter`` and ``participant``;
    ephemeral (RP) pulls leave both ``None``. The ``involved_*`` tuples carry
    the typed-FK pks that describe which anchors the action engages, so
    ``_anchor_in_action`` can avoid introspecting the action graph from inside
    the service layer (caller is responsible for populating them).

    ``excluded_kinds`` (#1919): when set, threads whose ``target_kind`` is in
    the set fail the anchor-in-action check **before** the
    ``_ALWAYS_IN_ACTION_KINDS`` shortcut. Social-action pulls pass
    ``frozenset({TargetKind.GIFT})`` so a GIFT thread (which is always
    in-action for casts where the technique IS the gift anchor) is rejected
    for social pulls where no gift technique is involved. Cast pulls leave
    this ``None`` (default).

    Distinct from ``actions.types.ActionContext`` — that dataclass is the
    generic action-resolver context with totally different fields.
    """

    combat_encounter: CombatEncounter | None = None
    participant: CombatParticipant | None = None
    involved_traits: tuple[int, ...] = ()
    involved_techniques: tuple[int, ...] = ()
    involved_objects: tuple[int, ...] = ()
    # The live target this pull's action is directed at (#1831). Feeds
    # ``apply_target_modulation`` in ``resolve_pull_effects``; None for
    # ephemeral / untargeted actions.
    target: ObjectDB | None = None
    # #1919: kinds excluded from the always-in-action shortcut (social pulls
    # exclude GIFT — no gift technique is the anchor of a social action).
    excluded_kinds: frozenset[str] | None = None


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
    scaled_value: int | None
    vital_target: str | None
    source_thread: Thread
    source_thread_level: int
    source_tier: int
    granted_capability: CapabilityType | None
    narrative_snippet: str
    inactive: bool = False
    inactive_reason: str | None = None
    target_form: CharacterForm | None = None
    # RESISTANCE only: the damage type this resistance mitigates (null = all types) (#1580).
    resistance_damage_type: DamageType | None = None


@dataclass(frozen=True)
class ResonancePullResult:
    """Result of ``spend_resonance_for_pull`` (Spec A §5.4 step 8)."""

    resonance_spent: int
    anima_spent: int
    resolved_effects: list[ResolvedPullEffect]


@dataclass(frozen=True)
class CastPullDeclaration:
    """A paid thread pull declared as part of an out-of-combat technique cast (#768).

    The caster commits ``resonance`` at ``tier`` across ``threads``; charged via
    ``spend_resonance_for_pull`` only after the cast clears its soulfray/pre-cast
    gates. All threads must share ``resonance`` and pass anchor-in-action checks.
    """

    resonance: Resonance
    tier: int
    threads: tuple[Thread, ...]
    beseech_bonus: int = 0
    """Emergency thread-bond draw bonus (#1718): added to the single COVENANT_ROLE
    thread's effective level for this pull's multiplier only — never persisted to
    Thread.level. 0 (default) means no emergency draw was invoked."""


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
