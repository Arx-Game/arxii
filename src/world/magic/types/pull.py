from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.utils.functional import cached_property

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.combat.models import CombatEncounter, CombatParticipant
    from world.conditions.models import CapabilityType, DamageType
    from world.forms.models import CharacterForm
    from world.magic.models import Resonance, Thread
    from world.magic.types.burn import BurnPreview


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

    @cached_property
    def involved_technique_closure(self) -> frozenset[int]:
        """``involved_techniques`` plus their transitive prerequisites (#4097).

        Ratified spec: a thread woven into a technique also empowers the
        techniques it is a prerequisite for (including hidden ultimates), at
        the thread's full level. ``_anchor_in_action``'s TECHNIQUE branch
        tests membership here instead of the bare ``involved_techniques``
        tuple so a prerequisite's thread carries through to what it unlocks.

        This is a ``cached_property`` on a per-call value object (not a
        SharedMemoryModel), so it is safe to memoize: it is computed once per
        ``PullActionContext`` instance, not once per thread, even though
        ``_anchor_in_action`` runs once per TECHNIQUE-kind thread in a sweep.
        Frozen dataclasses still carry an instance ``__dict__`` (no
        ``slots=True`` here), which is what ``cached_property`` writes into.
        """
        from world.magic.services.technique_prerequisites import (  # noqa: PLC0415
            prerequisite_technique_ids,
        )

        return frozenset(self.involved_techniques) | prerequisite_technique_ids(
            self.involved_techniques
        )


@dataclass(frozen=True)
class ResolvedPullEffect:
    """One resolved pull effect (per-thread × per-tier; Spec A §5.4 step 3).

    ``inactive`` flags VITAL_BONUS and RESISTANCE rows in ephemeral context —
    the cost is still paid in full but ``scaled_value`` is zeroed since there
    is no combat consumer for the bonus. CAPABILITY_GRANT is active in
    non-combat context (#2840). ``inactive_reason`` carries the player-facing
    explanation.
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
    # CAPABILITY_GRANT only: the frozen curved magnitude (#2730). None for
    # every other kind. Computed at resolve time via apply_capability_curve.
    capability_grant_value: int | None = None


@dataclass(frozen=True)
class ResonancePullResult:
    """Result of ``spend_resonance_for_pull`` (Spec A §5.4 step 8)."""

    resonance_spent: int
    anima_spent: int
    resolved_effects: list[ResolvedPullEffect]
    resonance_burned: int = 0


@dataclass(frozen=True)
class CastPullDeclaration:
    """A paid thread pull declared with a cast, a clash, or on its own (#768, #5066).

    The caster pulls ``threads`` at ``tier``; charged via ``spend_resonance_for_pull``
    only after the cast clears its soulfray/pre-cast gates. The threads may be of
    different resonances: each is paid from its own resonance at the tier's cost
    (maintainer ruling 2026-11-11). Every thread must pass the anchor-in-action check.
    """

    tier: int
    threads: tuple[Thread, ...]
    beseech_bonus: int = 0
    """Emergency thread-bond draw bonus (#1718): added to the single COVENANT_ROLE
    thread's effective level for this pull's multiplier only — never persisted to
    Thread.level. 0 (default) means no emergency draw was invoked."""
    burn: int = 0
    """Resonance points the caster asks to burn on top of the pull, for strain (#4736).
    0 (default) means no burn. The reached amount is resolved at cast time."""
    burn_resonance: Resonance | None = None
    """The pulled resonance the burn comes from, when the player named one (#5066). A pull
    of one resonance burns that one without naming it; see ``burned_resonance``."""

    @property
    def resonances(self) -> tuple[Resonance, ...]:
        """The distinct resonances of the pulled threads, in thread order."""
        seen: dict[int, Resonance] = {}
        for thread in self.threads:
            seen.setdefault(thread.resonance_id, thread.resonance)
        return tuple(seen.values())

    @property
    def burned_resonance(self) -> Resonance | None:
        """The resonance a burn on this pull comes from, or None when it cannot say.

        The named ``burn_resonance`` when it is one of the pulled resonances; the only
        pulled resonance when there is one; otherwise None (a burn on a mixed pull must
        name which resonance burns).
        """
        pulled = self.resonances
        if self.burn_resonance is not None:
            named = self.burn_resonance.pk
            return next((r for r in pulled if r.pk == named), None)
        return pulled[0] if len(pulled) == 1 else None


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
    #: The burn ceiling and per-point value for the technique the pull rides (#4736);
    #: None when the preview names no technique.
    burn: BurnPreview | None = None
