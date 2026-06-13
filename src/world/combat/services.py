"""Service functions for combat encounter lifecycle."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
import logging
import math
import random
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models.consequence_pools import ConsequencePool
    from typeclasses.characters import Character
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.checks.types import CheckResult, ModifierBreakdown, PendingResolution
    from world.combat.models import ClashConfig, StrainConfig
    from world.conditions.models import ConditionTemplate, DamageType
    from world.covenants.models import CovenantRole
    from world.magic.models import Technique
    from world.magic.types import TechniqueUseResult
    from world.magic.types.power_ledger import PowerLedger
    from world.scenes.models import Interaction, Persona

    PerformCheckFn = Callable[..., CheckResult]

from actions.errors import ActionDispatchError
from flows.constants import EventName
from flows.emit import emit_event
from flows.events.payloads import (
    AttackPreResolvePayload,
    CharacterIncapacitatedPayload,
    CharacterKilledPayload,
    DamageAppliedPayload,
    DamagePreApplyPayload,
    EncounterCompletedPayload,
)
from world.checks.constants import ModifierSourceKind
from world.checks.services import collect_check_modifiers, perform_check
from world.checks.types import ModifierContribution
from world.combat.constants import (
    DEFENSE_CRITICAL_MULTIPLIER,
    DEFENSE_FULL_MULTIPLIER,
    DEFENSE_NO_DAMAGE_THRESHOLD,
    DEFENSE_REDUCED_MULTIPLIER,
    DEFENSE_REDUCED_THRESHOLD,
    ENTITY_TYPE_NPC,
    ENTITY_TYPE_PC,
    FLEE_PARTIAL_SUCCESS_LEVEL,
    NO_ROLE_SPEED_RANK,
    NPC_SPEED_RANK,
    PENETRATION_CHECK_TYPE_NAME,
    ActionCategory,
    CombatManeuver,
    EncounterOutcome,
    EncounterStatus,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
    TargetingMode,
    TargetSelection,
)
from world.combat.damage_source import classify_source
from world.combat.models import (
    BossPhase,
    Clash,
    ClashContributionDeclaration,
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    CombatRoundAction,
    ComboDefinition,
    ComboLearning,
    ComboSlot,
    EncounterAftermathRule,
    EncounterRiskAcknowledgement,
    FleeConfig,
    FleeTierModifier,
    RoundChallengeDeclaration,
    ThreatPool,
    ThreatPoolEntry,
)
from world.combat.types import (
    ActionOutcome,
    AppliedConditionResult,
    AvailableCombo,
    ClashRoundResult,
    CombatTechniqueResolution,
    CombatTechniqueResult,
    ComboSlotMatch,
    DefenseResult,
    OpponentDamageResult,
    ParticipantDamageResult,
    PreparedClashContribution,
    RoundResolutionResult,
)
from world.fatigue.constants import EFFORT_CHECK_MODIFIER, EffortLevel
from world.fatigue.services import apply_fatigue, get_fatigue_penalty
from world.magic.constants import EffectKind
from world.mechanics.challenge_resolution import resolve_challenge
from world.mechanics.services import get_available_actions
from world.mechanics.types import ChallengeResolutionResult
from world.vitals.constants import (
    DEATH_HEALTH_THRESHOLD,
    KNOCKOUT_HEALTH_THRESHOLD,
    PERMANENT_WOUND_THRESHOLD,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Identity guard helpers
# ---------------------------------------------------------------------------


def is_combat_npc_typeclass(objectdb: ObjectDB) -> bool:
    """Return True iff the ObjectDB's typeclass is the CombatNPC class."""
    from world.combat.typeclasses.combat_npc import CombatNPC  # noqa: PLC0415

    return isinstance(objectdb, CombatNPC)


def has_persistent_identity_references(objectdb: ObjectDB) -> bool:
    """Return True if this ObjectDB is referenced by any model that signals
    persistent identity (Persona, RosterEntry, CharacterSheet, etc.).

    Single source of truth for "is this an ObjectDB any persistent system
    cares about?" — when a new persistent-identity model is added, this
    function adds the corresponding check.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    if CharacterSheet.objects.filter(character=objectdb).exists():
        return True
    if Persona.objects.filter(character_sheet__character=objectdb).exists():
        return True
    if RosterEntry.objects.filter(character_sheet__character=objectdb).exists():
        return True
    return False


def _character_has_death_deferred(character: ObjectDB) -> bool:  # noqa: OBJECTDB_PARAM
    """Return True if the character has any active condition granting death_deferred."""
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    return ConditionInstance.objects.filter(
        target=character,
        is_suppressed=False,
        resolved_at__isnull=True,
        condition__properties__name="death_deferred",
    ).exists()


def _emit_death_gate(character: Character, room: ObjectDB) -> None:  # noqa: OBJECTDB_PARAM
    """Fire the death gate: defer when death-deferred is active, else CHARACTER_KILLED."""
    if _character_has_death_deferred(character):
        from world.vitals.models import CharacterVitals  # noqa: PLC0415

        try:
            vitals = CharacterVitals.objects.get(character_sheet=character.sheet_data)
            vitals.death_deferred_pending = True
            vitals.save(update_fields=["death_deferred_pending"])
        except CharacterVitals.DoesNotExist:
            pass
    else:
        emit_event(
            EventName.CHARACTER_KILLED,
            CharacterKilledPayload(
                character=character,
                source_event=EventName.DAMAGE_PRE_APPLY,
            ),
            location=room,
        )


def get_penetration_check_type() -> CheckType:
    """Return the seeded 'penetration' CheckType for the ward contest (#639).

    Uses get() — never get_or_create — because this is authored content; a
    chartless fabricated row would silently break the resolution pipeline.
    If the seed is missing, CheckType.DoesNotExist propagates loudly (a real
    misconfiguration), not masked. Mirrors
    ``_get_endure_hallowed_ground_check_type``.
    """
    from world.checks.models import CheckType  # noqa: PLC0415

    return CheckType.objects.get(name=PENETRATION_CHECK_TYPE_NAME)


def get_flee_config() -> FleeConfig:
    """Return the seeded FleeConfig singleton (#878).

    Uses get() — never get_or_create — because this is authored content; a
    fabricated row would have no check_type and silently break flee
    resolution. DoesNotExist propagates loudly. Mirrors
    get_penetration_check_type.
    """
    return FleeConfig.objects.get(pk=1)


# ---------------------------------------------------------------------------
# CombatTechniqueResolver - Damage and condition resolution for combat techniques
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CombatTechniqueResolver:
    """Resolves the inner step of a combat-cast technique. Single class
    handles both damage and condition application; behavior differences
    live in technique-authored data (base_power, TechniqueAppliedCondition rows).
    """

    participant: CombatParticipant
    action: CombatRoundAction
    pull_flat_bonus: int
    fatigue_category: str
    offense_check_type: CheckType
    offense_check_fn: PerformCheckFn | None

    def _roll_check(self) -> CheckResult:
        """Roll the offense check with effort + pull-bonus modifiers."""
        check_fn = self.offense_check_fn or perform_check
        penalty = get_fatigue_penalty(
            self.participant.character_sheet,
            self.fatigue_category,
        )
        effort_mod = EFFORT_CHECK_MODIFIER.get(self.action.effort_level, 0)

        # Route effort AND the combat-pull flat bonus through the shared modifier
        # seam so the combat check honors condition + rollmod sources (the #851
        # individualization lever) and the recorded ModifierBreakdown is exhaustive:
        # every point that shifts the roll is a labeled contribution, so the
        # provenance UI can attribute it.  breakdown.total alone is the full roll
        # shift — no out-of-band additive the breakdown can't see.
        extra_contributions: list[ModifierContribution] = []
        if effort_mod:
            extra_contributions.append(
                ModifierContribution(
                    source_kind=ModifierSourceKind.EFFORT,
                    source_label="Effort",
                    value=effort_mod,
                )
            )
        if self.pull_flat_bonus:
            extra_contributions.append(
                ModifierContribution(
                    source_kind=ModifierSourceKind.PULL,
                    source_label="Combat pull",
                    value=self.pull_flat_bonus,
                )
            )
        breakdown = collect_check_modifiers(
            self.participant.character_sheet,
            self.offense_check_type,
            extra_contributions=extra_contributions,
        )
        extra_modifiers = breakdown.total
        character = self.participant.character_sheet.character
        return check_fn(
            character,
            self.offense_check_type,
            extra_modifiers=extra_modifiers,
            fatigue_penalty=penalty,
        )

    def _sum_intensity_bump_pulls(self) -> int:
        """Sum INTENSITY_BUMP scaled_values from active CombatPulls."""
        encounter = self.participant.encounter
        character = self.participant.character_sheet.character
        pull_bonus = 0
        for pull in character.combat_pulls.active_for_encounter(encounter):
            for eff in pull.resolved_effects_cached:
                if eff.kind == EffectKind.INTENSITY_BUMP and eff.scaled_value:
                    pull_bonus += eff.scaled_value
        return pull_bonus

    def _apply_damage(
        self, check_result: CheckResult, *, eff_intensity: int
    ) -> list[OpponentDamageResult]:
        """Iterate technique.damage_profiles. For each profile:
        - skip if SL < minimum_success_level
        - compute formula budget via compute_damage_budget
        - apply SL multiplier from DamageSuccessLevelMultiplier lookup
        - call apply_damage_to_opponent (which subtracts soak + resistance)
        Returns one OpponentDamageResult per applied component.
        Breaks on defeated target between components.
        """
        from world.conditions.services import get_damage_multiplier  # noqa: PLC0415

        target = self.action.focused_opponent_target
        if target is None:
            return []
        target.refresh_from_db()
        if target.status == OpponentStatus.DEFEATED:
            return []

        technique = self.action.focused_action
        profiles = list(
            technique.damage_profiles.select_related("damage_type").all(),
        )
        if not profiles:
            return []

        sl = check_result.success_level
        multiplier = get_damage_multiplier(sl)
        if multiplier <= 0:
            return []

        results: list[OpponentDamageResult] = []
        for profile in profiles:
            if sl < profile.minimum_success_level:
                continue
            budget = profile.compute_damage_budget(
                effective_power=eff_intensity,
                success_level=sl,
            )
            scaled = int(budget * multiplier)
            if scaled <= 0:
                continue
            target.refresh_from_db()
            if target.status == OpponentStatus.DEFEATED:
                break
            result = apply_damage_to_opponent(
                target,
                scaled,
                damage_type=profile.damage_type,
                source_sheet=self.participant.character_sheet,
            )
            results.append(result)
        return results

    def _apply_conditions(
        self,
        check_result: CheckResult,
        *,
        eff_intensity: int,
    ) -> list[AppliedConditionResult]:
        """Apply technique-authored conditions to appropriate targets.

        Iterates all TechniqueAppliedCondition rows on the technique, skips rows
        whose minimum_success_level exceeds the check result, resolves each row's
        target_kind to a concrete ObjectDB, computes severity/duration via the row's
        formula methods, and delegates to bulk_apply_conditions for the whole batch.

        ``eff_intensity`` is the combined effective intensity (injected power + pull bumps)
        computed by ``__call__`` and forwarded here.
        """
        from world.conditions.services import bulk_apply_conditions  # noqa: PLC0415
        from world.conditions.types import BulkConditionApplication  # noqa: PLC0415

        technique = self.action.focused_action
        sl = check_result.success_level
        rows = list(technique.condition_applications.select_related("condition").all())
        if not rows:
            return []

        caster_od = self.participant.character_sheet.character

        bulk_applications: list[BulkConditionApplication] = []
        for row in rows:
            if sl < row.minimum_success_level:
                continue
            target = _resolve_condition_target(row.target_kind, self.action, caster_od)
            if target is None:
                continue
            severity = row.compute_severity(
                effective_power=eff_intensity,
                success_level=sl,
            )
            duration = row.compute_duration_rounds(
                effective_power=eff_intensity,
                success_level=sl,
            )
            bulk_applications.append(
                BulkConditionApplication(
                    target=target,
                    template=row.condition,
                    severity=severity,
                    duration_rounds=duration,
                    stack_count=row.stack_count,
                )
            )

        if not bulk_applications:
            return []

        bulk_results = bulk_apply_conditions(
            bulk_applications,
            source_character=caster_od,
            source_technique=technique,
        )
        out: list[AppliedConditionResult] = []
        for app, result in zip(bulk_applications, bulk_results, strict=True):
            out.append(
                AppliedConditionResult(
                    target=app.target,
                    condition=app.template,
                    severity_applied=app.severity,
                    duration_rounds=app.duration_rounds,
                    success=result.success,
                )
            )
        return out

    def _apply_penetration(self, combat_ledger: PowerLedger) -> tuple[PowerLedger, bool]:
        """Run the penetration-vs-resistance contest (#639) against the ward.

        The penetration difficulty is the focused opponent's
        ``barrier_strength`` (the ward ONLY — damage-type resistance is soaked
        once downstream in ``apply_damage_to_opponent``; never consumed here).

        Caster-side modifiers flow through ``collect_check_modifiers`` (the
        same seam as the offense check), so condition/equipment and
        check-scoped CharacterModifier sources all apply (#767).

        Returns ``(ledger, bounced)``:

        - No focused opponent / no barrier (None or 0) → UNOPPOSED: returns
          the ledger unchanged and ``bounced=False``, rolls NO check, adds NO
          entry. Inert for every existing combat path (those targets carry no
          barrier) — a zero-power unwarded cast still flows to its base_damage.
        - factor == 0 → bounce: a PENETRATION ``set 0`` entry and
          ``bounced=True`` (the caller short-circuits damage/conditions).
        - pct == 0 (factor 1.00, clean penetration) → a PENETRATION ``set``
          entry with the unchanged total and ``bounced=False``. Power is
          unmodified, but the entry lets narration distinguish a
          warded-but-cleanly-penetrated cast from an unwarded one.
        - pct != 0 (partial or overpenetration) → a PENETRATION ``multiply``
          entry by ``(factor - 1) * 100`` pct and ``bounced=False``.
        """
        from world.conditions.services import get_penetration_factor  # noqa: PLC0415
        from world.magic.constants import PowerStage  # noqa: PLC0415
        from world.magic.types.power_ledger import PowerLedgerBuilder  # noqa: PLC0415

        target = self.action.focused_opponent_target
        ward = (target.barrier_strength or 0) if target is not None else 0
        if ward <= 0:
            return combat_ledger, False

        caster = self.participant.character_sheet.character
        pen_check_type = get_penetration_check_type()
        # Mirror _roll_check: route through the shared modifier seam so the
        # penetration contest honors condition / rollmod / equipment
        # and CHARACTER (#767, e.g. "+penetration vs warded foes") sources.
        # Effort and pull bonuses stay offense-only, exactly as #639 decided.
        pen_breakdown = collect_check_modifiers(
            self.participant.character_sheet,
            pen_check_type,
        )
        pen_result = perform_check(
            caster,
            pen_check_type,
            target_difficulty=ward,
            extra_modifiers=pen_breakdown.total,
        )
        factor = get_penetration_factor(pen_result.success_level)
        builder = PowerLedgerBuilder.from_ledger(combat_ledger)
        if factor == 0:
            return builder.set_value(PowerStage.PENETRATION, "ward (bounced)", 0).build(), True
        pct = round((float(factor) - 1.0) * 100)
        if pct == 0:
            # Clean full penetration: record the event without changing power so
            # narration can distinguish a warded-but-cleanly-penetrated cast from
            # an unwarded one (which records NO entry at all).
            return (
                builder.set_value(
                    PowerStage.PENETRATION, "ward (penetrated)", combat_ledger.total
                ).build(),
                False,
            )
        return builder.multiply(PowerStage.PENETRATION, "ward", pct).build(), False

    def __call__(self, *, power: int, ledger: PowerLedger) -> CombatTechniqueResolution:  # noqa: ARG002
        """Resolve the combat technique inner step.

        ``power`` is injected by ``use_technique`` after the PRE_CAST envelope
        (it equals stats.intensity including identity modifiers, and may have
        been further modified by a pre-cast MODIFY_PAYLOAD hook).  INTENSITY_BUMP
        pull bonuses from the current round are added on top inside this method
        so the final effective intensity = power + pull intensity bumps.

        ``ledger`` is the per-cast :class:`PowerLedger` carrying all stages up
        to and including the environment power-shift.  The resolver appends a
        ``COMBAT_PULL`` stage for the INTENSITY_BUMP bonuses sourced from active
        :class:`~world.combat.models.CombatPull` rows and builds a per-target
        ledger whose ``total`` equals the final effective intensity forwarded to
        damage and condition resolution.
        """
        from world.magic.constants import PowerStage  # noqa: PLC0415
        from world.magic.types.power_ledger import PowerLedgerBuilder  # noqa: PLC0415

        pull_bonus = self._sum_intensity_bump_pulls()
        combat_ledger = (
            PowerLedgerBuilder.from_ledger(ledger)
            .add(PowerStage.COMBAT_PULL, "combat pulls", pull_bonus)
            .build()
        )
        check_result = self._roll_check()

        # Penetration-vs-resistance contest (#639): if the focused target has a
        # ward (barrier_strength > 0), the caster rolls a penetration check
        # against the ward and the resulting factor SCALES power before it
        # enters the unchanged damage/condition path. Unwarded targets are
        # unopposed — no check, no ledger entry, behavior identical to pre-#639.
        combat_ledger, bounced = self._apply_penetration(combat_ledger)
        eff_intensity = combat_ledger.total

        if bounced:
            # Bounced off the ward: no damage, no conditions. The returned
            # ledger still records the bounce so narration can pose it. (A
            # legitimately zero-power UNWARDED cast does NOT take this path —
            # it still flows to base_damage downstream.)
            return CombatTechniqueResolution(
                check_result=check_result,
                damage_results=[],
                applied_conditions=[],
                pull_flat_bonus=self.pull_flat_bonus,
                scaled_damage=0,
                power_ledger=combat_ledger,
            )

        damage_results = self._apply_damage(check_result, eff_intensity=eff_intensity)
        applied_conditions = self._apply_conditions(check_result, eff_intensity=eff_intensity)
        return CombatTechniqueResolution(
            check_result=check_result,
            damage_results=damage_results,
            applied_conditions=applied_conditions,
            pull_flat_bonus=self.pull_flat_bonus,
            scaled_damage=sum(r.damage_dealt for r in damage_results),
            power_ledger=combat_ledger,
        )


def _sum_active_flat_bonuses(
    participant: CombatParticipant,
    encounter: CombatEncounter,
) -> int:
    """Sum scaled_value across FLAT_BONUS resolved-effect rows on the
    participant's active CombatPull rows for this encounter.

    Reads through CharacterCombatPullHandler so the cached/prefetched
    list is honored — avoids re-querying.
    """
    character = participant.character_sheet.character
    total = 0
    for pull in character.combat_pulls.active_for_encounter(encounter):
        for eff in pull.resolved_effects_cached:
            if eff.kind == EffectKind.FLAT_BONUS and eff.scaled_value:
                total += eff.scaled_value
    return total


def compute_intensity_for_clash(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> int:
    """Return technique.intensity + active INTENSITY_BUMP pull bonuses for the clash floor gate.

    Used exclusively to gate the clash-open check (intensity_floor). Future
    intensity-ramp contributions (conditions, items, environment) can be added
    here and they will tighten the floor automatically.
    """
    technique = action.focused_action
    if technique is None:
        return 0
    base = technique.intensity
    encounter = participant.encounter
    pull_bonus = 0
    character = participant.character_sheet.character
    for pull in character.combat_pulls.active_for_encounter(encounter):
        for eff in pull.resolved_effects_cached:
            if eff.kind == EffectKind.INTENSITY_BUMP and eff.scaled_value:
                pull_bonus += eff.scaled_value
    return base + pull_bonus


def _resolve_condition_target(
    kind: str,
    action: CombatRoundAction,
    caster_od: ObjectDB,
) -> ObjectDB | None:
    """Resolve a ConditionTargetKind value to a concrete ObjectDB.

    Returns None when the named target is absent or ineligible (e.g. opponent
    already DEFEATED).
    """
    from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415

    if kind == ConditionTargetKind.SELF:
        return caster_od
    if kind == ConditionTargetKind.ALLY:
        ally = action.focused_ally_target
        return ally.character_sheet.character if ally is not None else None
    if kind == ConditionTargetKind.ENEMY:
        opp = action.focused_opponent_target
        if opp is not None:
            opp.refresh_from_db()
        active = opp is not None and opp.status != OpponentStatus.DEFEATED
        return opp.objectdb if active else None
    return None


def _build_affected_targets(
    participant: CombatParticipant,  # noqa: ARG001 - reserved for future signature additions
    action: CombatRoundAction,
) -> list[ObjectDB]:
    """Return the dedup'd ObjectDB list for use_technique's targets parameter.

    Resolution rules:
    - opponent target → opp.objectdb (always present after CombatOpponent refactor;
      None-guarded for pathological state)
    - ally target → ally.character_sheet.character
    - both null → empty list
    """
    targets: list = []
    seen: set[int] = set()
    if action.focused_opponent_target_id:
        opp = action.focused_opponent_target
        od = opp.objectdb
        if od is not None and od.pk not in seen:
            targets.append(od)
            seen.add(od.pk)
    if action.focused_ally_target_id:
        ally_od = action.focused_ally_target.character_sheet.character
        if ally_od.pk not in seen:
            targets.append(ally_od)
            seen.add(ally_od.pk)
    return targets


def _build_combat_result(
    technique_use_result: TechniqueUseResult,
    resolver: CombatTechniqueResolver,  # noqa: ARG001 - kept for future extensibility
) -> CombatTechniqueResult:
    """Translate use_technique's outcome into the adapter's return shape."""
    if not technique_use_result.confirmed:
        return CombatTechniqueResult(
            damage_results=[],
            applied_conditions=[],
            technique_use_result=technique_use_result,
        )

    resolution = technique_use_result.resolution_result
    # Defensive assertion against programmer error — service contract
    # is that combat resolvers return CombatTechniqueResolution.
    if not isinstance(resolution, CombatTechniqueResolution):
        msg = f"Expected CombatTechniqueResolution, got {type(resolution).__name__}"
        raise TypeError(msg)

    return CombatTechniqueResult(
        damage_results=list(resolution.damage_results),
        applied_conditions=list(resolution.applied_conditions),
        technique_use_result=technique_use_result,
        power_ledger=resolution.power_ledger,
    )


def resolve_combat_technique(
    *,
    participant: CombatParticipant,
    action: CombatRoundAction,
    fatigue_category: str,
    offense_check_type: CheckType,
    offense_check_fn: PerformCheckFn | None,
) -> CombatTechniqueResult:
    """Route a damage-path combat technique through use_technique.

    Builds a CombatTechniqueResolver and passes it to use_technique as
    resolve_fn. The magic envelope handles anima, soulfray, mishap,
    PRE_CAST/CAST events, reactive scar interception, and corruption.
    The resolver does the offense check + damage application inside
    that envelope.

    Soulfray warning is auto-confirmed at round resolution time —
    frontend handles preview before submission.

    TECHNIQUE_AFFECTED fires per target via _build_affected_targets:
    opponent target → opp.objectdb; ally target → ally character ObjectDB.

    Other pull effect kinds are deferred:
    - INTENSITY_BUMP: needs runtime stats to accept combat context
    - CAPABILITY_GRANT: tied to non-attack pipeline
    - NARRATIVE_ONLY: cosmetic surfacing
    - VITAL_BONUS: already wired through recompute_max_health_with_threads
    """
    from world.magic.services import use_technique  # noqa: PLC0415

    encounter = participant.encounter
    pull_flat_bonus = _sum_active_flat_bonuses(participant, encounter)

    resolver = CombatTechniqueResolver(
        participant=participant,
        action=action,
        pull_flat_bonus=pull_flat_bonus,
        fatigue_category=fatigue_category,
        offense_check_type=offense_check_type,
        offense_check_fn=offense_check_fn,
    )

    targets = _build_affected_targets(participant, action)

    technique_use_result = use_technique(
        character=participant.character_sheet.character,
        technique=action.focused_action,
        resolve_fn=resolver,
        confirm_soulfray_risk=True,
        targets=targets,
    )

    return _build_combat_result(technique_use_result, resolver)


def _ensure_combat_engagement(participant: CombatParticipant) -> None:
    """Ensure the participant's character holds an engagement (combat-owned, #872).

    Existing non-combat engagements are preserved (begin_engagement contract);
    such participants do not tick or spike this encounter.
    """
    from world.mechanics.constants import EngagementType  # noqa: PLC0415
    from world.mechanics.services import begin_engagement  # noqa: PLC0415

    begin_engagement(
        participant.character_sheet.character,
        EngagementType.COMBAT,
        source=participant.encounter,
    )


def add_participant(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
    *,
    covenant_role: CovenantRole | None = None,
) -> CombatParticipant:
    """Create a CombatParticipant linking a PC to an encounter.

    When no role is supplied, default to the character's combat-precedence role
    (Battle wins over Durance — Slice E).
    """
    if covenant_role is None:
        from world.covenants.services import precedence_role_for_combat  # noqa: PLC0415

        covenant_role = precedence_role_for_combat(character_sheet)
    participant = CombatParticipant.objects.create(
        encounter=encounter,
        character_sheet=character_sheet,
        covenant_role=covenant_role,
    )
    _ensure_combat_engagement(participant)
    return participant


def remove_participant(participant: CombatParticipant) -> None:
    """Remove a participant: status write + combat engagement teardown (#872)."""
    from world.mechanics.constants import EngagementType  # noqa: PLC0415
    from world.mechanics.services import end_engagement  # noqa: PLC0415

    participant.status = ParticipantStatus.REMOVED
    participant.save(update_fields=["status"])
    end_engagement(
        participant.character_sheet.character,
        EngagementType.COMBAT,
        source=participant.encounter,
    )


def acknowledge_encounter_risk(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
) -> EncounterRiskAcknowledgement:
    """Idempotently record that a character acknowledged the encounter's risk (#777).

    Called at every voluntary entry: self-join, hostile-cast initiation, and
    consent-accept. The level is snapshotted at first acknowledgement.
    """
    ack, _created = EncounterRiskAcknowledgement.objects.get_or_create(
        encounter=encounter,
        character_sheet=character_sheet,
        defaults={"acknowledged_risk_level": encounter.risk_level},
    )
    return ack


def join_encounter(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
    *,
    covenant_role: CovenantRole | None = None,
) -> CombatParticipant:
    """Allow a PC to join an active combat encounter.

    Can join during DECLARING or BETWEEN_ROUNDS status.
    Raises ValueError if already participating or encounter is completed.
    """
    allowed = {EncounterStatus.DECLARING, EncounterStatus.BETWEEN_ROUNDS}
    if encounter.status not in allowed:
        msg = "Can only join during declaration or between rounds."
        raise ValueError(msg)

    # Query instead of cache — write path needs fresh data to prevent races.
    # The unique constraint is the real safety net.
    if CombatParticipant.objects.filter(
        encounter=encounter,
        character_sheet=character_sheet,
        status=ParticipantStatus.ACTIVE,
    ).exists():
        msg = "Already participating in this encounter."
        raise ValueError(msg)

    if covenant_role is None:
        from world.covenants.services import precedence_role_for_combat  # noqa: PLC0415

        covenant_role = precedence_role_for_combat(character_sheet)
    participant = CombatParticipant.objects.create(
        encounter=encounter,
        character_sheet=character_sheet,
        covenant_role=covenant_role,
        status=ParticipantStatus.ACTIVE,
    )
    _ensure_combat_engagement(participant)
    acknowledge_encounter_risk(encounter, character_sheet)
    return participant


def declare_flee(participant: CombatParticipant) -> CombatRoundAction:
    """Declare intent to flee -- passives-only maneuver, auto-ready.

    Creates or replaces the current round's CombatRoundAction with no
    focused action and maneuver=FLEE. Flee resolves as a real check at
    round resolution (_resolve_flee); the participant remains ACTIVE until
    the check succeeds.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter

    # Encounter status check
    if encounter.status != EncounterStatus.DECLARING:
        msg = (
            f"Cannot flee: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot flee: participant is no longer active in this encounter."
        raise ValueError(msg)

    # Vitality check — dead characters cannot flee. Unconscious / dying
    # characters may still be dragged out (flee is passives-only).
    if is_dead(participant.character_sheet):
        msg = "Cannot flee: character is dead."
        raise ValueError(msg)
    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.VERY_LOW,
            "focused_opponent_target": None,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.FLEE,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def declare_cover(
    participant: CombatParticipant,
    ally: CombatParticipant,
) -> CombatRoundAction:
    """Declare a covering maneuver for an ally -- passives-only, auto-ready.

    Cover resolves as a no-op on its own; its effect is the FleeConfig
    cover_bonus it contributes to the ally's flee check in _resolve_flee.
    Covering an ally who never declares flee simply wastes the action.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != EncounterStatus.DECLARING:
        msg = (
            f"Cannot cover: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot cover: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot cover: character is dead."
        raise ValueError(msg)
    if ally.pk == participant.pk:
        msg = "Cannot cover yourself."
        raise ValueError(msg)
    if ally.encounter_id != encounter.pk or ally.status != ParticipantStatus.ACTIVE:
        msg = "Cover target must be an active participant in this encounter."
        raise ValueError(msg)
    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.VERY_LOW,
            "focused_opponent_target": None,
            "focused_ally_target": ally,
            "maneuver": CombatManeuver.COVER,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def add_opponent(  # noqa: PLR0913 - opponent creation requires all stat fields
    encounter: CombatEncounter,
    *,
    name: str,
    tier: str,
    max_health: int,
    threat_pool: ThreatPool | None,
    description: str = "",
    soak_value: int = 0,
    probing_threshold: int | None = None,
    persona: Persona | None = None,
    existing_objectdb: ObjectDB | None = None,
) -> CombatOpponent:
    """Create a CombatOpponent. Three sources for the ObjectDB:

    - existing_objectdb: pre-existing OD (PvP, named NPC w/o persona). Never ephemeral.
    - persona: reuses persona's character ObjectDB. Never ephemeral.
    - neither: creates a new CombatNPC OD scoped to this encounter. Ephemeral.
    """
    from evennia.utils.create import create_object  # noqa: PLC0415

    from typeclasses.characters import Character  # noqa: PLC0415
    from world.combat.typeclasses.combat_npc import CombatNPC  # noqa: PLC0415

    if existing_objectdb is not None and not isinstance(existing_objectdb, Character):
        msg = (
            f"existing_objectdb must be a Character typeclass instance "
            f"(got {type(existing_objectdb).__name__}). "
            f"Combat damage paths require character.conditions handler access."
        )
        raise TypeError(msg)

    if existing_objectdb is not None:
        objectdb = existing_objectdb
        is_ephemeral = False
    elif persona is not None:
        objectdb = persona.character_sheet.character
        is_ephemeral = False
    else:
        if encounter.room is None:
            msg = "Cannot create ephemeral CombatNPC: encounter has no room."
            raise ValueError(msg)
        objectdb = create_object(CombatNPC, key=name, location=encounter.room, nohome=True)
        is_ephemeral = True

    opp = CombatOpponent(
        encounter=encounter,
        name=name,
        tier=tier,
        max_health=max_health,
        health=max_health,
        threat_pool=threat_pool,
        description=description,
        soak_value=soak_value,
        probing_threshold=probing_threshold,
        persona=persona,
        objectdb=objectdb,
        objectdb_is_ephemeral=is_ephemeral,
    )
    opp.full_clean()
    opp.save()
    return opp


@transaction.atomic
def begin_declaration_phase(encounter: CombatEncounter) -> None:
    """Advance round_number by 1 and set status to DECLARING.

    Uses select_for_update to prevent concurrent calls.
    Raises ValueError if the encounter is not BETWEEN_ROUNDS.
    """
    enc = CombatEncounter.objects.select_for_update().get(pk=encounter.pk)
    if enc.status != EncounterStatus.BETWEEN_ROUNDS:
        msg = (
            f"Cannot begin declaration phase: encounter status is "
            f"'{enc.get_status_display()}', expected 'Between Rounds'."
        )
        raise ValueError(msg)

    has_opponents = CombatOpponent.objects.filter(
        encounter=enc,
        status=OpponentStatus.ACTIVE,
    ).exists()
    if not has_opponents:
        msg = "Cannot begin declaration phase: no active opponents in encounter."
        raise ValueError(msg)

    enc.round_number += 1
    enc.status = EncounterStatus.DECLARING
    enc.round_started_at = timezone.now()
    enc.save(update_fields=["round_number", "status", "round_started_at"])

    # --- Round-start per-participant upkeep: DoT tick + engagement ensure ---
    from world.conditions.services import process_round_start  # noqa: PLC0415

    active_participants_start = CombatParticipant.objects.filter(
        encounter=enc,
        status=ParticipantStatus.ACTIVE,
    ).select_related("character_sheet__character")
    for p in active_participants_start:
        process_round_start(p.character_sheet.character)
        # Permanent idempotency safety net: any participant that reached this
        # point without a combat engagement (however they were created) gets
        # one ensured here so all downstream engagement-dependent paths are safe.
        _ensure_combat_engagement(p)

    active_opponents_start = CombatOpponent.objects.filter(
        encounter=enc,
        status=OpponentStatus.ACTIVE,
    ).select_related("objectdb")
    for opp in active_opponents_start:
        if opp.objectdb is not None:
            process_round_start(opp.objectdb)

    # --- Escalation tick (#872): opted-in encounters build pressure each round ---
    from world.combat.escalation import (  # noqa: PLC0415
        apply_escalation_tick,
        install_escalation_room_triggers,
    )

    if enc.escalation_curve is not None:
        install_escalation_room_triggers(enc)
        apply_escalation_tick(enc)

    # Spec A §3.8 + §7.4 lines 2031–2039: expire pulls for the previous
    # round *after* round_number has advanced so the < comparison catches
    # the old rows. recompute_max_health_with_threads runs per affected
    # participant inside expire_pulls_for_round (clamp-not-injure).
    expire_pulls_for_round(enc)
    # Refresh the caller's instance so it reflects the new state.
    encounter.refresh_from_db()


def expire_pulls_for_round(encounter: CombatEncounter) -> None:
    """Delete all CombatPull rows from prior rounds and recompute affected max_health.

    Spec A §3.8 lines 1057–1078 + §7.4 lines 2031–2039. Called from
    ``begin_declaration_phase`` immediately after ``round_number`` advances.

    - Collects distinct ``participant_id``s whose pulls are about to expire.
    - Cascade-deletes the stale ``CombatPull`` rows (the FK cascade drops
      their ``CombatPullResolvedEffect`` children).
    - Invalidates each affected participant's ``CharacterCombatPullHandler``
      cache so the next read of ``combat_pulls.active_pull_vital_bonuses``
      reflects the deletion.
    - Calls ``recompute_max_health_with_threads`` per participant so any
      expiring MAX_HEALTH pull goes away via the clamp-not-injure path in
      ``vitals.recompute_max_health`` — characters are never *injured* by
      a pull expiring, only un-bolstered.

    Side-effect-free for participants with no active pulls this encounter.
    """
    from world.combat.models import CombatPull  # noqa: PLC0415
    from world.magic.services import (  # noqa: PLC0415
        recompute_max_health_with_threads,
    )

    stale_pulls = CombatPull.objects.filter(
        encounter=encounter,
        round_number__lt=encounter.round_number,
    )
    affected_participant_ids = list(stale_pulls.values_list("participant_id", flat=True).distinct())
    if not affected_participant_ids:
        return

    stale_pulls.delete()

    # Re-fetch participants so we can walk to character_sheet.character —
    # SharedMemoryModel returns the identity-mapped instances, so this is
    # zero-query once the participants have been loaded in the request.
    participants = CombatParticipant.objects.filter(
        pk__in=affected_participant_ids,
    ).select_related("character_sheet__character")
    for p in participants:
        p.character_sheet.character.combat_pulls.invalidate()
        recompute_max_health_with_threads(p.character_sheet)


def _validate_passive_slot(
    focused_category: str | None,
    *,
    physical_passive: Technique | None,
    social_passive: Technique | None,
    mental_passive: Technique | None,
) -> None:
    """Raise if the passive slot matching ``focused_category`` is occupied."""
    if focused_category is None:
        return
    passive_map = {
        ActionCategory.PHYSICAL: physical_passive,
        ActionCategory.SOCIAL: social_passive,
        ActionCategory.MENTAL: mental_passive,
    }
    if passive_map.get(focused_category) is not None:
        msg = (
            f"Cannot declare action: {focused_category} passive must be "
            f"None when focused_category is {focused_category}."
        )
        raise ValueError(msg)


def _supplied_target_kind(
    participant: CombatParticipant,
    focused_ally_target: CombatParticipant | None,
    focused_opponent_target: CombatOpponent | None,
) -> object | None:
    """Map the supplied target to its ConditionTargetKind, or None if no target."""
    from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415

    if focused_ally_target is not None:
        if focused_ally_target == participant:
            return ConditionTargetKind.SELF
        return ConditionTargetKind.ALLY
    if focused_opponent_target is not None:
        return ConditionTargetKind.ENEMY
    return None


def _validate_target_kind_alignment(
    participant: CombatParticipant,
    focused_action: Technique,
    focused_ally_target: CombatParticipant | None,
    focused_opponent_target: CombatOpponent | None,
) -> None:
    """Raise if the supplied target's kind is not accepted by the technique."""
    from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415

    rows = list(focused_action.condition_applications.all())
    has_base_power = focused_action.effect_type.base_power is not None

    if rows:
        kinds = {row.target_kind for row in rows}
        target_supplied_kind = _supplied_target_kind(
            participant, focused_ally_target, focused_opponent_target
        )
        # Accept SELF/ALLY interchangeably for ally-targets
        accepted = kinds.copy()
        if ConditionTargetKind.ALLY in accepted:
            accepted.add(ConditionTargetKind.SELF)
        if ConditionTargetKind.SELF in accepted:
            accepted.add(ConditionTargetKind.ALLY)
        if target_supplied_kind is not None and target_supplied_kind not in accepted:
            msg = (
                f"Technique target_kinds {sorted(kinds)} do not match supplied "
                f"target kind '{target_supplied_kind}'."
            )
            raise ValueError(msg)

    if has_base_power and not rows and focused_opponent_target is None:
        msg = "Damage technique requires focused_opponent_target."
        raise ValueError(msg)


def declare_action(  # noqa: PLR0913 - action declaration requires all slot fields
    participant: CombatParticipant,
    *,
    focused_action: Technique | None = None,
    focused_category: str | None = None,
    effort_level: str,
    focused_opponent_target: CombatOpponent | None = None,
    focused_ally_target: CombatParticipant | None = None,
    physical_passive: Technique | None = None,
    social_passive: Technique | None = None,
    mental_passive: Technique | None = None,
) -> CombatRoundAction:
    """Declare a PC's action for the current round.

    Validations:
    - Participant must be able to act (not dead and not incapacitated) — see can_act.
      A dying-but-conscious character keeps awareness and passes naturally.
    - Encounter must be in DECLARING status.
    - Round number must match encounter's current round.
    - The passive slot matching the focused_category must be None.
    - focused_opponent_target and focused_ally_target are mutually exclusive.
    - focused_action's condition_applications target_kinds must match the supplied target.
    - A pure-damage technique (base_power, no condition rows) requires focused_opponent_target.

    Raises ValueError with clear messages for validation failures.
    """

    from world.vitals.services import can_act  # noqa: PLC0415

    encounter = participant.encounter

    # The focused technique's authored category is authoritative (#614): it drives
    # which passive slot must stay empty. Override any client-supplied value.
    if focused_action is not None:
        focused_category = focused_action.action_category

    # Agency check — not dead and not incapacitated. A dying-but-conscious
    # character keeps awareness and passes naturally (no dying_final_round concept).
    if not can_act(participant.character_sheet):
        msg = "Cannot declare action: character is dead or incapacitated."
        raise ValueError(msg)

    # Encounter status check
    if encounter.status != EncounterStatus.DECLARING:
        msg = (
            f"Cannot declare action: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    # Passive slot validation (only when a focused category is declared)
    _validate_passive_slot(
        focused_category,
        physical_passive=physical_passive,
        social_passive=social_passive,
        mental_passive=mental_passive,
    )

    if focused_opponent_target and focused_opponent_target.status != OpponentStatus.ACTIVE:
        msg = "Cannot target a defeated opponent."
        raise ValueError(msg)

    # XOR target validation
    if focused_opponent_target and focused_ally_target:
        msg = "Action cannot target both an opponent and an ally."
        raise ValueError(msg)

    # Target-kind alignment with technique authoring
    if focused_action is not None:
        _validate_target_kind_alignment(
            participant,
            focused_action,
            focused_ally_target,
            focused_opponent_target,
        )

    action, _created = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": focused_action,
            "focused_category": focused_category,
            "effort_level": effort_level,
            "focused_opponent_target": focused_opponent_target,
            "focused_ally_target": focused_ally_target,
            "physical_passive": physical_passive,
            "social_passive": social_passive,
            "mental_passive": mental_passive,
            "maneuver": None,  # Reset maneuver on re-declaration
            "combo_upgrade": None,  # Reset combo on re-declaration
            "is_ready": False,  # Reset ready on re-declaration
        },
    )
    return action


def _get_eligible_entries(
    opponent: CombatOpponent,
    entries: list[ThreatPoolEntry],
    cooldown_used_entry_ids: set[int],
) -> list[ThreatPoolEntry]:
    """Return threat pool entries eligible for this opponent's current state.

    Args:
        opponent: The opponent selecting an action.
        entries: Pre-fetched threat pool entries for this opponent's pool.
        cooldown_used_entry_ids: Entry IDs recently used (within cooldown window)
            by this opponent. Pre-fetched in batch by the caller.
    """
    eligible: list[ThreatPoolEntry] = []
    for entry in entries:
        # Filter by minimum_phase
        if entry.minimum_phase is not None and entry.minimum_phase > opponent.current_phase:
            continue

        # Filter by cooldown — check against pre-fetched set
        if entry.cooldown_rounds is not None and entry.pk in cooldown_used_entry_ids:
            continue

        eligible.append(entry)

    return eligible


def _select_targets(
    entry: ThreatPoolEntry,
    active_participants: list[CombatParticipant],
) -> list[CombatParticipant]:
    """Select targets for a threat pool entry from active participants."""
    if not active_participants:
        return []

    mode = entry.targeting_mode
    selection = entry.target_selection

    if mode == TargetingMode.ALL:
        return list(active_participants)

    count = 1
    if mode == TargetingMode.MULTI:
        count = entry.target_count or 1

    count = min(count, len(active_participants))

    if selection == TargetSelection.LOWEST_HEALTH:
        from world.vitals.models import CharacterVitals  # noqa: PLC0415

        sheet_ids = [p.character_sheet_id for p in active_participants]
        health_map = dict(
            CharacterVitals.objects.filter(
                character_sheet_id__in=sheet_ids,
            ).values_list("character_sheet_id", "health")
        )
        sorted_by_health = sorted(
            active_participants,
            key=lambda p: health_map.get(p.character_sheet_id, 0),
        )
        return sorted_by_health[:count]

    if selection == TargetSelection.RANDOM:
        return random.sample(active_participants, count)

    # TODO: SPECIFIC_ROLE should prioritize tank covenant role (aggro system)
    # TODO: HIGHEST_THREAT should use a threat tracking mechanic (not yet built)
    # Placeholder: pick first active participants by DB order
    return list(active_participants[:count])


def _batch_fetch_cooldown_data(
    opponents: list[CombatOpponent],
    entries_by_pool: dict[int, list[ThreatPoolEntry]],
    all_entries: list[ThreatPoolEntry],
    round_number: int,
) -> dict[int, set[int]]:
    """Batch-fetch recently-used entry IDs per opponent for cooldown checks.

    Returns a mapping of opponent_id -> set of entry IDs that are on cooldown.
    """
    cooldown_filters = Q()
    for opponent in opponents:
        opp_entries = entries_by_pool.get(opponent.threat_pool_id, [])
        cooldown_entry_ids = [e.pk for e in opp_entries if e.cooldown_rounds is not None]
        if not cooldown_entry_ids:
            continue
        max_cooldown = max(e.cooldown_rounds for e in opp_entries if e.cooldown_rounds is not None)
        earliest_allowed = max(1, round_number - max_cooldown + 1)
        cooldown_filters |= Q(
            opponent=opponent,
            threat_entry_id__in=cooldown_entry_ids,
            round_number__gte=earliest_allowed,
        )

    result: dict[int, set[int]] = defaultdict(set)
    if not cooldown_filters:
        return result

    recent_actions = CombatOpponentAction.objects.filter(cooldown_filters).values_list(
        "opponent_id", "threat_entry_id", "round_number"
    )
    entry_cooldown_map = {
        e.pk: e.cooldown_rounds for e in all_entries if e.cooldown_rounds is not None
    }
    for opp_id, entry_id, round_num in recent_actions:
        cooldown = entry_cooldown_map.get(entry_id)
        if cooldown is not None:
            earliest = max(1, round_number - cooldown + 1)
            if round_num >= earliest:
                result[opp_id].add(entry_id)

    return result


def select_npc_actions(
    encounter: CombatEncounter,
) -> list[CombatOpponentAction]:
    """Select and create NPC actions for the current round.

    For each active opponent with a threat pool, picks a weighted-random
    entry from eligible threat pool entries and assigns targets.

    Raises ValueError if the encounter is not in DECLARING status.
    """
    if encounter.status != EncounterStatus.DECLARING:
        msg = (
            f"Cannot select NPC actions: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    opponents = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
        )
        .exclude(threat_pool__isnull=True)
        .select_related("threat_pool")
    )

    if not opponents:
        return []

    # Batch-prefetch all threat pool entries for all opponent pools
    pool_ids = {o.threat_pool_id for o in opponents if o.threat_pool_id}
    all_entries = list(ThreatPoolEntry.objects.filter(pool_id__in=pool_ids))
    entries_by_pool: dict[int, list[ThreatPoolEntry]] = defaultdict(list)
    for entry in all_entries:
        entries_by_pool[entry.pool_id].append(entry)

    recently_used_by_opponent = _batch_fetch_cooldown_data(
        opponents,
        entries_by_pool,
        all_entries,
        encounter.round_number,
    )

    # Design: NPCs target PCs who can still act (not dead, not incapacitated).
    # Unconscious PCs (awareness 0) are "down" and not picked as targets; a
    # dying-but-conscious PC remains in the fight and is targetable. can_act is
    # the same coarse agency gate used for declaration eligibility.
    from world.vitals.services import can_act  # noqa: PLC0415

    candidate_participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        ).select_related("character_sheet__character")
    )
    active_participants = [p for p in candidate_participants if can_act(p.character_sheet)]

    actions: list[CombatOpponentAction] = []

    for opponent in opponents:
        pool_entries = entries_by_pool.get(opponent.threat_pool_id, [])
        cooldown_used = recently_used_by_opponent.get(opponent.pk, set())
        eligible = _get_eligible_entries(opponent, pool_entries, cooldown_used)
        if not eligible:
            continue

        if opponent.tier == OpponentTier.SWARM and opponent.swarm_count is not None:
            n_attacks = swarm_attack_count(
                opponent.swarm_count,
                opponent.bodies_per_attack or 1,
                len(active_participants),
            )
        else:
            n_attacks = 1

        for _ in range(n_attacks):
            weights = [e.weight for e in eligible]
            chosen = random.choices(eligible, weights=weights, k=1)[0]  # noqa: S311
            targets = _select_targets(chosen, active_participants)
            action = CombatOpponentAction.objects.create(
                opponent=opponent,
                round_number=encounter.round_number,
                threat_entry=chosen,
            )
            action.targets.set(targets)
            actions.append(action)

    return actions


def swarm_kills(raw_damage: int, body_toughness: int) -> int:
    """Bodies a single landing attack clears from a swarm (#875).

    A landing hit always clears at least one body; big hits mow through many.
    ``body_toughness`` is the damage needed per body.
    """
    if raw_damage <= 0:
        return 0
    return max(1, raw_damage // max(1, body_toughness))


def swarm_attack_count(swarm_count: int, bodies_per_attack: int, active_pc_count: int) -> int:
    """Attacks a swarm makes this round — scales with remaining bodies (#875).

    Capped at the number of PCs who can act, so a swarm fans across the party
    rather than dogpiling one PC. Derived on read; nothing persisted.
    """
    if swarm_count <= 0 or active_pc_count <= 0:
        return 0
    raw = math.ceil(swarm_count / max(1, bodies_per_attack))
    return max(1, min(raw, active_pc_count))


def apply_damage_to_opponent(
    opponent: CombatOpponent,
    raw_damage: int,
    *,
    bypass_soak: bool = False,
    damage_type: DamageType | None = None,
    source_sheet: CharacterSheet | None = None,
) -> OpponentDamageResult:
    """Apply damage to an NPC opponent, accounting for soak, probing,
    and damage-type resistance.

    All raw damage (even fully soaked) contributes to probing. Only damage
    that exceeds soak and resistance actually reduces health.

    When ``source_sheet`` is provided, increments the source's achievement
    counters: ``damage_dealt`` (by post-soak damage), and on defeat
    ``opponents_defeated``.
    """
    # Swarm: no HP, no soak, no probing -- a landing attack clears bodies.
    if opponent.tier == OpponentTier.SWARM and opponent.swarm_count is not None:
        kills = min(swarm_kills(raw_damage, opponent.body_toughness or 1), opponent.swarm_count)
        opponent.swarm_count -= kills
        defeated = opponent.swarm_count <= 0
        if defeated:
            opponent.status = OpponentStatus.DEFEATED
        opponent.save(update_fields=["swarm_count", "status"])
        del source_sheet
        return OpponentDamageResult(
            damage_dealt=kills,
            health_damaged=False,
            probed=False,
            probing_increment=0,
            defeated=defeated,
            kills=kills,
        )

    effective_soak = 0 if bypass_soak else opponent.soak_value

    resistance = 0
    if damage_type is not None and opponent.objectdb is not None:
        resistance = opponent.objectdb.conditions.resistance_modifier(damage_type)

    damage_through = max(0, raw_damage - effective_soak - resistance)
    # Combo damage that bypasses soak should not also probe — the combo
    # itself is the reward for probing.
    probing_increment = 0 if bypass_soak else max(0, raw_damage)

    opponent.health -= damage_through
    # ``increment_probing`` is the sibling standalone write site for the no-damage
    # passive path (combo-opening passives). This write stays inline because it
    # shares a single combined save with health/status below; ``probing_increment``
    # is already ``max(0, …)`` so both paths apply the same non-negative clamp.
    opponent.probing_current += probing_increment

    # Hero Killer cannot be defeated -- narrative immunity ("you must run").
    defeated = opponent.health <= 0 and opponent.tier != OpponentTier.HERO_KILLER
    if defeated:
        opponent.status = OpponentStatus.DEFEATED

    opponent.save(update_fields=["health", "probing_current", "status"])

    # Achievement counters: see world.combat.achievement_counters. Wired in
    # a follow-up phase — keeping the source_sheet kwarg in place so the
    # call sites are pre-threaded.
    del source_sheet

    return OpponentDamageResult(
        damage_dealt=damage_through,
        health_damaged=damage_through > 0,
        probed=probing_increment > 0,
        probing_increment=probing_increment,
        defeated=defeated,
        kills=0,
    )


def increment_probing(opponent: CombatOpponent, amount: int) -> None:
    """Add ``amount`` to an opponent's probing counter (clamped at zero) and persist.

    Single standalone write path for ``probing_current`` used by combo-opening
    passives so probing feeds combo detection identically to damage-sourced probing.
    """
    opponent.probing_current = max(0, opponent.probing_current + amount)
    opponent.save(update_fields=["probing_current"])


def _apply_passive_technique(
    technique: Technique,
    participant: CombatParticipant,
    encounter: CombatEncounter,
) -> None:
    """Apply a declared passive technique's authored conditions with NO dice roll.

    A passive IS a Technique with authored ``TechniqueAppliedCondition`` rows.
    Each row is applied at fixed scaling — ``effective_power=technique.intensity``
    and ``success_level=row.minimum_success_level`` — so no ``CheckResult`` is
    constructed and no offense roll happens (contrast ``CombatTechniqueResolver``,
    which is roll/damage-bound). Reuses ``bulk_apply_conditions`` so passives feed
    the exact same condition machinery as the focused path.

    Target resolution (v1):

    - ``SELF`` → the actor's own character.
    - ``ENEMY`` → every ACTIVE opponent's ``objectdb``. Mirrors
      ``_resolve_condition_target``'s ENEMY branch, which returns ``opp.objectdb``
      for an active opponent. Every opponent (including ephemeral CombatNPCs) is
      created with an ObjectDB by ``add_opponent``; the FK is only nulled if the
      ObjectDB is destroyed externally, so we skip opponents whose ``objectdb`` is
      None — matching the focused path's None-guard.
    - ``ALLY`` → every ACTIVE participant except the actor.

    When ``technique.combo_opening_probing`` is set, every ACTIVE opponent gains
    that much probing (the combo-opening reward) via ``increment_probing`` — this
    is the combo-opening effect for ephemeral opponents regardless of conditions.
    """
    from world.conditions.services import bulk_apply_conditions  # noqa: PLC0415
    from world.conditions.types import BulkConditionApplication  # noqa: PLC0415
    from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415

    actor = participant.character_sheet.character

    # Batch the opponent/ally queries ONCE before the row loop (no queries in loop).
    active_opponents = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
        ).select_related("objectdb")
    )
    active_allies = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        .exclude(pk=participant.pk)
        .select_related("character_sheet__character")
    )

    # Combo-opening probing: granted to every active opponent independent of any
    # condition application (the combo-opening effect for ephemeral opponents).
    if technique.combo_opening_probing:
        for opp in active_opponents:
            increment_probing(opp, technique.combo_opening_probing)

    # resolve_round prefetches ``..._passive__condition_applications__condition`` so
    # this ``.all()`` reads the prefetch cache (no per-passive query in the resolution
    # loop). Standalone callers fall back to lazy loads. Do NOT add ``.select_related``
    # here — it forces a fresh query and bypasses the prefetch cache.
    rows = list(technique.condition_applications.all())
    if not rows:
        return

    applications: list[BulkConditionApplication] = []
    for row in rows:
        severity = row.compute_severity(
            effective_power=technique.intensity,
            success_level=row.minimum_success_level,
        )
        duration = row.compute_duration_rounds(
            effective_power=technique.intensity,
            success_level=row.minimum_success_level,
        )

        if row.target_kind == ConditionTargetKind.SELF:
            targets = [actor]
        elif row.target_kind == ConditionTargetKind.ENEMY:
            targets = [opp.objectdb for opp in active_opponents if opp.objectdb is not None]
        elif row.target_kind == ConditionTargetKind.ALLY:
            targets = [ally.character_sheet.character for ally in active_allies]
        else:
            targets = []

        applications.extend(
            BulkConditionApplication(
                target=target,
                template=row.condition,
                severity=severity,
                duration_rounds=duration,
                stack_count=row.stack_count,
            )
            for target in targets
        )

    if not applications:
        return

    bulk_apply_conditions(
        applications,
        source_character=actor,
        source_technique=technique,
        source_description=f"passive: {technique.name}",
    )


def _resolve_passive_actions(
    encounter: CombatEncounter,
    pc_actions: dict[int, CombatRoundAction],
) -> None:
    """Apply every declared passive on every PC action before focused resolution.

    Runs before ``_resolve_actions`` so defensive/buff passives land before any
    focused or NPC action resolves this round.
    """
    for action in pc_actions.values():
        for passive in (
            action.physical_passive,
            action.social_passive,
            action.mental_passive,
        ):
            if passive is not None:
                _apply_passive_technique(passive, action.participant, encounter)


def apply_damage_to_participant(  # noqa: PLR0913
    participant: CombatParticipant,
    damage: int,
    *,
    force_death: bool = False,
    damage_type: DamageType | None = None,
    source: object | None = None,
    source_sheet: CharacterSheet | None = None,
) -> ParticipantDamageResult:
    """Apply damage to a PC via their CharacterVitals.

    Does NOT roll for knockout/death/wounds — only reports eligibility.
    The caller is responsible for acting on the result.

    When ``source_sheet`` is provided (e.g. PC vs PC damage), increments the
    source's ``damage_dealt`` counter. The target always gets a
    ``damage_received`` increment (regardless of source).

    Emits reactive events:
    - DAMAGE_PRE_APPLY (cancellable, mutable amount)
    - DAMAGE_APPLIED (post-save, frozen)
    - CHARACTER_INCAPACITATED (only on the transition into the knockout band,
      and only when the death gate does not also fire — death supersedes)
    - CHARACTER_KILLED (if death_eligible or force_death)
    """
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    vitals = CharacterVitals.objects.get(
        character_sheet=participant.character_sheet,
    )

    character = participant.character_sheet.character
    room = character.location
    damage_source = classify_source(source)

    # --- DAMAGE_PRE_APPLY (cancellable, amount may be modified) ---
    pre_payload = DamagePreApplyPayload(
        target=character,
        amount=damage,
        damage_type=damage_type,
        source=damage_source,
    )
    if room is not None:
        stack = emit_event(
            EventName.DAMAGE_PRE_APPLY,
            pre_payload,
            location=room,
        )
        if stack.was_cancelled():
            return ParticipantDamageResult(
                damage_dealt=0,
                health_after=vitals.health,
                knockout_eligible=False,
                death_eligible=False,
                permanent_wound_eligible=False,
            )

    # Use the (possibly modified) amount from the payload
    effective_damage = pre_payload.amount

    # Thread-derived damage reduction (Spec A §5.8 lines 1658–1668).
    # Inlined here rather than a flow subscriber because the flow/event
    # system dispatches on FlowDefinition rows, not Python callables
    # (see Phase 13 Open Item 3). Reads handler caches; near-zero cost.
    from world.magic.services import (  # noqa: PLC0415
        apply_damage_reduction_from_threads,
    )

    effective_damage = apply_damage_reduction_from_threads(character, effective_damage)

    if damage_type is not None:
        resistance = character.conditions.resistance_modifier(damage_type)
        effective_damage = max(0, effective_damage - resistance)

    health_before = vitals.health
    vitals.health -= effective_damage
    health_after = vitals.health

    if vitals.max_health > 0:
        health_pct = max(0.0, health_after / vitals.max_health)
        health_before_pct = max(0.0, health_before / vitals.max_health)
    else:
        health_pct = 0.0
        health_before_pct = 0.0

    knockout_eligible = (
        health_pct <= KNOCKOUT_HEALTH_THRESHOLD and health_after > DEATH_HEALTH_THRESHOLD
    )
    # Same band test applied to pre-hit health — used only to latch the
    # CHARACTER_INCAPACITATED emit to the transition into the band.
    was_in_knockout_band = (
        health_before_pct <= KNOCKOUT_HEALTH_THRESHOLD and health_before > DEATH_HEALTH_THRESHOLD
    )
    death_eligible = health_after <= DEATH_HEALTH_THRESHOLD
    permanent_wound_eligible = effective_damage > (vitals.max_health * PERMANENT_WOUND_THRESHOLD)

    # Incapacitation / dying state is no longer written here. It is applied by
    # process_damage_consequences (Bleeding-Out / Unconscious conditions) which
    # the caller invokes after damage. force_death still drives the
    # CHARACTER_KILLED event below; the dying condition itself comes from the
    # consequence pipeline — no stray vitals.status write.
    vitals.save(update_fields=["health"])

    # Achievement counters: see world.combat.achievement_counters. Wired in
    # a follow-up phase — keeping the source_sheet kwarg in place so the
    # call sites are pre-threaded.
    del source_sheet

    # --- DAMAGE_APPLIED (post-save, frozen) ---
    applied_payload = DamageAppliedPayload(
        target=character,
        amount_dealt=effective_damage,
        damage_type=pre_payload.damage_type,
        source=damage_source,
        hp_after=health_after,
    )
    if room is not None:
        emit_event(
            EventName.DAMAGE_APPLIED,
            applied_payload,
            location=room,
        )

        # --- Incapacitation / death gates ---
        # CHARACTER_INCAPACITATED marks the dramatic beat (the fall), not
        # per-hit at-risk status: it fires only on the transition INTO the
        # knockout band, and never alongside the death gate — one narrative
        # beat, one event. knockout_eligible itself stays per-hit for the
        # survivability-check pipeline (process_damage_consequences).
        will_emit_death_gate = death_eligible or force_death
        if knockout_eligible and not was_in_knockout_band and not will_emit_death_gate:
            emit_event(
                EventName.CHARACTER_INCAPACITATED,
                CharacterIncapacitatedPayload(
                    character=character,
                    source_event=EventName.DAMAGE_PRE_APPLY,
                ),
                location=room,
            )

        if will_emit_death_gate:
            _emit_death_gate(character, room)

    return ParticipantDamageResult(
        damage_dealt=effective_damage,
        health_after=health_after,
        knockout_eligible=knockout_eligible,
        death_eligible=death_eligible,
        permanent_wound_eligible=permanent_wound_eligible,
    )


def get_resolution_order(
    encounter: CombatEncounter,
) -> list[tuple[str, CombatParticipant | CombatOpponent]]:
    """Build the resolution order for a combat round.

    Returns a sorted list of (entity_type, entity) tuples where entity_type
    is "pc" or "npc". Sorted by speed rank ascending (lower = faster).

    Includes:
    - PCs who can_act (not dead, not incapacitated; dying-but-conscious included)
      (speed from covenant_role or NO_ROLE_SPEED_RANK)
    - ACTIVE NPCs (all at NPC_SPEED_RANK)

    Excludes:
    - UNCONSCIOUS PCs (awareness 0 → cannot act)
    - DEAD PCs
    - DEFEATED/FLED NPCs
    """
    from world.vitals.services import can_act  # noqa: PLC0415

    participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        ).select_related("covenant_role", "character_sheet__character")
    )

    ranked: list[tuple[int, str, CombatParticipant | CombatOpponent]] = []
    for p in participants:
        if not can_act(p.character_sheet):
            continue
        speed = p.covenant_role.speed_rank if p.covenant_role_id else NO_ROLE_SPEED_RANK
        ranked.append((speed, ENTITY_TYPE_PC, p))

    opponents = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
        )
    )
    ranked.extend((NPC_SPEED_RANK, ENTITY_TYPE_NPC, o) for o in opponents)

    ranked.sort(key=lambda item: (item[0], item[2].pk))

    return [(entity_type, entity) for _, entity_type, entity in ranked]


# ---------------------------------------------------------------------------
# Combo detection
# ---------------------------------------------------------------------------


def _action_matches_slot(
    action: CombatRoundAction,
    slot: ComboSlot,
    gift_resonance_ids: dict[int, set[int]],
) -> bool:
    """Check whether a PC's declared action satisfies a combo slot.

    A slot matches when:
    1. The technique's effect_type matches the slot's required_action_type.
    2. If the slot has a resonance_requirement, the technique's gift must
       have a matching resonance (via the gift's M2M resonances).

    Args:
        action: The PC's declared round action.
        slot: The combo slot to test against.
        gift_resonance_ids: Pre-fetched mapping of gift_id -> set of resonance IDs.
    """
    technique = action.focused_action
    if technique is None:
        return False
    if technique.effect_type_id != slot.required_action_type_id:
        return False
    if slot.resonance_requirement_id is not None:
        resonance_ids = gift_resonance_ids.get(technique.gift_id, set())
        if slot.resonance_requirement_id not in resonance_ids:
            return False
    return True


def _try_match_all_slots(
    slots: list[ComboSlot],
    actions: list[CombatRoundAction],
    gift_resonance_ids: dict[int, set[int]],
) -> list[ComboSlotMatch] | None:
    """Try to assign one action per slot using backtracking.

    Returns a list of ``ComboSlotMatch`` if all slots match, or ``None``.
    Backtracking ensures order-independent matching for combos with 2-5 slots.
    """
    assignment: dict[int, CombatRoundAction] = {}
    used_action_ids: set[int] = set()

    def backtrack(slot_idx: int) -> bool:
        if slot_idx >= len(slots):
            return True
        slot = slots[slot_idx]
        for action in actions:
            if action.pk in used_action_ids:
                continue
            if _action_matches_slot(action, slot, gift_resonance_ids):
                assignment[slot.pk] = action
                used_action_ids.add(action.pk)
                if backtrack(slot_idx + 1):
                    return True
                del assignment[slot.pk]
                used_action_ids.discard(action.pk)
        return False

    if not backtrack(0):
        return None

    return [
        ComboSlotMatch(
            slot_number=slot.slot_number,
            participant=assignment[slot.pk].participant,
            action=assignment[slot.pk],
        )
        for slot in slots
    ]


def _prefetch_clash_state(
    encounter: CombatEncounter,
    active_opponents: list[CombatOpponent],
) -> tuple[set[str], set[int]]:
    """Prefetch clash-state data needed for combo prerequisite checks.

    Executes exactly two queries regardless of the number of combos or
    opponents: one for clash flavors (ACTIVE or RESOLVED), one for
    window-condition template IDs on opponent ObjectDBs.

    Args:
        encounter: The combat encounter.
        active_opponents: Already-fetched list of ACTIVE ``CombatOpponent`` rows.

    Returns:
        A 2-tuple of:
        - ``encounter_clash_flavors``: set of flavor strings for ACTIVE **or
          RESOLVED** clashes in this encounter.  A resolved clash still
          enables combos that require its flavor — e.g. a LOCK clash that
          resolved with a decisive PC win leaves boss_held on the NPC, and
          the clash_window_combo (required_clash_flavor=LOCK) should still
          be available.  The window-condition field on the combo is the
          precise gate; this field is a coarse "has this encounter seen
          this clash type" check.
        - ``active_window_condition_template_ids``: set of ``ConditionTemplate``
          PKs that are active on at least one opponent ObjectDB.
    """
    from world.combat.constants import ClashStatus  # noqa: PLC0415
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    # Include both ACTIVE and RESOLVED clashes: the window combo is available
    # even after the LOCK resolves, as long as the boss_held window condition
    # is still active on the NPC.
    encounter_clash_flavors: set[str] = set(
        Clash.objects.filter(
            encounter=encounter,
            status__in=(ClashStatus.ACTIVE, ClashStatus.RESOLVED),
        ).values_list("flavor", flat=True)
    )

    opponent_objectdb_ids = {opp.objectdb_id for opp in active_opponents if opp.objectdb_id}
    active_window_condition_template_ids: set[int] = set()
    if opponent_objectdb_ids:
        active_window_condition_template_ids = set(
            ConditionInstance.objects.filter(
                target_id__in=opponent_objectdb_ids,
            ).values_list("condition_id", flat=True)
        )

    return encounter_clash_flavors, active_window_condition_template_ids


def _combo_passes_clash_prereqs(
    combo: ComboDefinition,
    encounter_clash_flavors: set[str],
    active_window_condition_template_ids: set[int],
) -> bool:
    """Return True iff the combo's clash-state prerequisites are satisfied.

    Both fields are optional; a null field imposes no constraint.

    Args:
        combo: The combo definition to check.
        encounter_clash_flavors: Set of clash-flavor strings for any clash (ACTIVE or
            RESOLVED) in the encounter. RESOLVED clashes are included because combo
            eligibility runs after ``_resolve_clashes`` and a combo gated on
            ``required_clash_flavor`` should still see the just-resolved clash's flavor.
        active_window_condition_template_ids: Set of ``ConditionTemplate`` PKs active
            on any opponent ObjectDB in the encounter.
    """
    if combo.required_clash_flavor and combo.required_clash_flavor not in encounter_clash_flavors:
        return False
    if (
        combo.required_clash_window_condition_id
        and combo.required_clash_window_condition_id not in active_window_condition_template_ids
    ):
        return False
    return True


def _build_available_combo(  # noqa: PLR0913 - prefetched availability inputs
    combo: ComboDefinition,
    *,
    actions: list[CombatRoundAction],
    gift_resonance_ids: dict[int, set[int]],
    known_map: dict[int, set[int]],
    participant_sheet_ids: set[int],
    max_probing: int,
    encounter_clash_flavors: set[str],
    active_window_condition_template_ids: set[int],
) -> AvailableCombo | None:
    """Return an ``AvailableCombo`` if ``combo`` is fully available, else None.

    Applies the availability gates in order: slots present, minimum probing,
    known-or-discoverable, clash-state prerequisites, and slot matching.
    """
    slots: list[ComboSlot] = combo.cached_slots
    if not slots:
        return None

    # Check minimum probing requirement
    if combo.minimum_probing is not None and max_probing < combo.minimum_probing:
        return None

    # Determine if any participant knows the combo
    knowers = known_map.get(combo.pk, set())
    known_by_any = bool(knowers & participant_sheet_ids)
    if not known_by_any and not combo.discoverable_via_combat:
        return None

    # Check clash-state prerequisites (flavor + window condition)
    if not _combo_passes_clash_prereqs(
        combo, encounter_clash_flavors, active_window_condition_template_ids
    ):
        return None

    # Backtracking slot matching: each slot must be filled by a distinct action
    slot_matches = _try_match_all_slots(slots, actions, gift_resonance_ids)
    if slot_matches is None:
        return None

    return AvailableCombo(
        combo=combo,
        slot_matches=slot_matches,
        known_by_participant=known_by_any,
    )


def detect_available_combos(
    encounter: CombatEncounter,
    round_number: int,
) -> list[AvailableCombo]:
    """Scan declared actions to find combos whose slots are all satisfied.

    A combo is available when:
    - Every slot is matched by a distinct participant's focused action.
    - The combo's ``minimum_probing`` (if set) is met by at least one active
      opponent in the encounter.
    - At least one participating PC knows the combo (``ComboLearning``) **or**
      the combo is ``discoverable_via_combat``.
    - Clash-state prerequisites are satisfied (two prefetches per call, not per combo):
      - If ``required_clash_flavor`` is set, an active ``Clash`` of that flavor
        must exist in the encounter.
      - If ``required_clash_window_condition`` is set, a ``ConditionInstance`` of
        that ``ConditionTemplate`` must be active on at least one opponent in the
        encounter.

    Args:
        encounter: The combat encounter.
        round_number: The round whose actions to scan.

    Returns:
        List of ``AvailableCombo`` instances with slot→participant mappings.
    """
    actions = list(
        CombatRoundAction.objects.filter(
            participant__encounter=encounter,
            round_number=round_number,
            focused_action__isnull=False,
        ).select_related(
            "participant",
            "participant__character_sheet",
            "focused_action",
            "focused_action__effect_type",
            "focused_action__gift",
        )
    )
    if not actions:
        return []

    # Pre-fetch gift -> resonance_ids mapping to avoid N+1 in slot matching
    from world.magic.models import Gift  # noqa: PLC0415

    gift_ids = {a.focused_action.gift_id for a in actions}
    gift_resonance_ids: dict[int, set[int]] = defaultdict(set)
    for gift_id, res_id in Gift.resonances.through.objects.filter(gift_id__in=gift_ids).values_list(
        "gift_id", "resonance_id"
    ):
        gift_resonance_ids[gift_id].add(res_id)

    # Pre-filter combos to only those whose slots reference declared effect types
    effect_type_ids = {a.focused_action.effect_type_id for a in actions}
    combos = list(
        ComboDefinition.objects.filter(
            slots__required_action_type_id__in=effect_type_ids,
        )
        .distinct()
        .prefetch_related(
            Prefetch(
                "slots",
                queryset=ComboSlot.objects.select_related(
                    "required_action_type",
                ).order_by("slot_number"),
                to_attr="cached_slots",
            ),
        )
    )

    # Pre-fetch which characters know which combos (one query)
    participant_sheet_ids = {a.participant.character_sheet_id for a in actions}
    known_combos_qs = ComboLearning.objects.filter(
        character_sheet_id__in=participant_sheet_ids,
    ).values_list("combo_id", "character_sheet_id")
    known_map: dict[int, set[int]] = defaultdict(set)
    for combo_id, sheet_id in known_combos_qs:
        known_map[combo_id].add(sheet_id)

    # Max probing across active opponents for minimum_probing check
    max_probing = 0
    active_opponents = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
        )
    )
    for opp in active_opponents:
        max_probing = max(max_probing, opp.probing_current)

    # Prefetch clash-state for combo prerequisite checks (two queries total).
    encounter_clash_flavors, active_window_condition_template_ids = _prefetch_clash_state(
        encounter, active_opponents
    )

    available: list[AvailableCombo] = []

    for combo in combos:
        result = _build_available_combo(
            combo,
            actions=actions,
            gift_resonance_ids=gift_resonance_ids,
            known_map=known_map,
            participant_sheet_ids=participant_sheet_ids,
            max_probing=max_probing,
            encounter_clash_flavors=encounter_clash_flavors,
            active_window_condition_template_ids=active_window_condition_template_ids,
        )
        if result is not None:
            available.append(result)

    return available


def run_combo_detection(
    encounter: CombatEncounter,
    round_number: int,
) -> list[AvailableCombo]:
    """Public entry point for combo detection during the DECLARING phase.

    Call this between action declaration and resolution to detect available
    combos and allow players to upgrade actions. ``resolve_round`` also
    calls ``detect_available_combos`` internally for informational reporting,
    but combo upgrades via ``upgrade_action_to_combo`` should happen during
    DECLARING — before resolution begins.
    """
    return detect_available_combos(encounter, round_number)


def upgrade_action_to_combo(
    action: CombatRoundAction,
    combo: ComboDefinition,
) -> None:
    """Mark a PC's round action as upgraded to a combo.

    Args:
        action: The CombatRoundAction to upgrade.
        combo: The ComboDefinition being activated.
    """
    action.combo_upgrade = combo
    action.save(update_fields=["combo_upgrade_id"])


def revert_combo_upgrade(action: CombatRoundAction) -> None:
    """Remove a combo upgrade from a round action, reverting to normal.

    Args:
        action: The CombatRoundAction to revert.
    """
    action.combo_upgrade = None
    action.save(update_fields=["combo_upgrade_id"])


# ---------------------------------------------------------------------------
# Defensive check integration
# ---------------------------------------------------------------------------


def _damage_multiplier_for_success(success_level: int) -> float:
    """Map a check success_level to a damage multiplier.

    Args:
        success_level: The ``CheckResult.success_level`` value.

    Returns:
        Float multiplier applied to NPC base damage.
    """
    if success_level >= DEFENSE_NO_DAMAGE_THRESHOLD:
        return 0.0
    if success_level >= DEFENSE_REDUCED_THRESHOLD:
        return DEFENSE_REDUCED_MULTIPLIER
    if success_level <= -1:
        return DEFENSE_CRITICAL_MULTIPLIER
    return DEFENSE_FULL_MULTIPLIER


def resolve_npc_attack(
    opponent_action: CombatOpponentAction,
    participant: CombatParticipant,
    check_type: CheckType,
    *,
    perform_check_fn: PerformCheckFn | None = None,
) -> DefenseResult:
    """Resolve one NPC attack against one PC via a defensive check.

    The PC rolls ``perform_check`` against the NPC's attack. The success
    level determines a damage multiplier applied to the threat entry's
    ``base_damage``.

    Args:
        opponent_action: The NPC's chosen action for the round.
        participant: The targeted PC.
        check_type: The CheckType matching the attack's category.
        perform_check_fn: Optional callable override for testing. Defaults
            to ``world.checks.services.perform_check``.

    Returns:
        A ``DefenseResult`` containing the check outcome and damage applied.
    """
    if perform_check_fn is None:
        from world.checks.services import perform_check as perform_check_fn  # noqa: PLC0415

    character = participant.character_sheet.character
    room = character.location

    # --- ATTACK_PRE_RESOLVE (cancellable) ---
    pre_payload = AttackPreResolvePayload(
        attacker=opponent_action.opponent,
        targets=[character],
        weapon=None,
        action=opponent_action,
    )
    if room is not None:
        stack = emit_event(
            EventName.ATTACK_PRE_RESOLVE,
            pre_payload,
            location=room,
        )
        if stack.was_cancelled():
            return DefenseResult(
                success_level=0,
                damage_multiplier=0.0,
                final_damage=0,
                damage_result=ParticipantDamageResult(
                    damage_dealt=0,
                    health_after=0,
                    knockout_eligible=False,
                    death_eligible=False,
                    permanent_wound_eligible=False,
                ),
            )

    result: CheckResult = perform_check_fn(character, check_type)

    multiplier = _damage_multiplier_for_success(result.success_level)
    base_damage = opponent_action.threat_entry.base_damage
    final_damage = math.floor(base_damage * multiplier)

    damage_result = apply_damage_to_participant(
        participant,
        final_damage,
        damage_type=opponent_action.threat_entry.damage_type,
        source=opponent_action.opponent,
    )

    return DefenseResult(
        success_level=result.success_level,
        damage_multiplier=multiplier,
        final_damage=final_damage,
        damage_result=damage_result,
    )


# ---------------------------------------------------------------------------
# Boss phase transitions
# ---------------------------------------------------------------------------


def check_and_advance_boss_phase(
    opponent: CombatOpponent,
) -> BossPhase | None:
    """Check whether a boss should advance to the next phase and apply it.

    Transition happens when the boss's health drops to or below a phase's
    ``health_trigger_percentage``. The next phase (by ``phase_number``) whose
    trigger is satisfied and whose ``phase_number`` is greater than the
    opponent's ``current_phase`` is activated.

    On transition:
    - ``opponent.current_phase`` advances.
    - ``threat_pool``, ``soak_value`` are swapped from the new phase.
    - ``probing_current`` is reset to zero.
    - If the new phase has a ``probing_threshold``, it overwrites the
      opponent's ``probing_threshold``.

    Args:
        opponent: The boss opponent to check.

    Returns:
        The ``BossPhase`` that was activated, or ``None`` if no transition.
    """
    phases = list(
        BossPhase.objects.filter(
            opponent=opponent,
            phase_number__gt=opponent.current_phase,
        ).order_by("phase_number")
    )

    health_pct = opponent.health_percentage

    for phase in phases:
        if phase.health_trigger_percentage is None:
            continue
        if health_pct <= phase.health_trigger_percentage:
            opponent.current_phase = phase.phase_number
            if phase.threat_pool_id:
                opponent.threat_pool = phase.threat_pool
            opponent.soak_value = phase.soak_value
            opponent.probing_current = 0
            if phase.probing_threshold is not None:
                opponent.probing_threshold = phase.probing_threshold
            opponent.save(
                update_fields=[
                    "current_phase",
                    "threat_pool_id",
                    "soak_value",
                    "probing_current",
                    "probing_threshold",
                ],
            )
            return phase

    return None


# ---------------------------------------------------------------------------
# Round resolution orchestrator
# ---------------------------------------------------------------------------


def _record_combat_consequence(  # noqa: PLR0913 - mirrors record_consequence_outcome's fields
    sheet: CharacterSheet,
    check_type: CheckType,
    pool: ConsequencePool,
    pending: PendingResolution,
    breakdown: ModifierBreakdown,
    *,
    interaction: Interaction | None,
    summary: str,
) -> None:
    """Persist ConsequenceOutcome provenance for a pool-routed combat resolution.

    Mirrors vitals' _record_combat_outcome guard: a sourceless ConsequenceOutcome
    is forbidden, so skip when no interaction anchor exists (sheet without a
    PRIMARY persona). Shared by flee and encounter-aftermath resolution.
    """
    if interaction is None:
        return

    from actions.types import WeightedConsequence  # noqa: PLC0415
    from world.checks.services import record_consequence_outcome  # noqa: PLC0415

    selected = pending.selected_consequence
    if isinstance(selected, WeightedConsequence):
        selected = selected.consequence
    record_consequence_outcome(
        sheet,
        check_type,
        pool,
        selected if selected.pk is not None else None,
        breakdown,
        combat_interaction=interaction,
        summary=summary,
    )


def _resolve_flee(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> ActionOutcome:
    """Resolve a declared flee as a graded check (#878).

    Difficulty = FleeConfig.base_difficulty + max(FleeTierModifier over active
    opponents' tiers); zero active opponents → tier term 0 (no auto-success).
    Each same-round COVER declaration by an ACTIVE participant whose
    focused_ally_target is this participant adds FleeConfig.cover_bonus.

    Graded outcome by success_level: PARTIAL (-1) or better escapes
    (status → FLED); PARTIAL and below applies the selected pool consequence
    (PARTIAL = escape at a cost; FAILURE/BOTCH = stays ACTIVE). Botch severity
    is authored in the pool's BOTCH-tier entries, not special-cased here.
    """
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_resolution,
        resolve_pool_consequences,
        select_consequence,
    )
    from world.checks.types import ResolutionContext  # noqa: PLC0415

    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))
    config = get_flee_config()
    encounter = participant.encounter

    # Difficulty: base + the single worst (max) modifier among active
    # opponents' tiers. One values_list + one filter — no queries in loops.
    active_tiers = set(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
        ).values_list("tier", flat=True)
    )
    tier_modifiers = dict(
        FleeTierModifier.objects.filter(tier__in=active_tiers).values_list(
            "tier", "difficulty_modifier"
        )
    )
    tier_term = max((tier_modifiers.get(tier, 0) for tier in active_tiers), default=0)
    difficulty = config.base_difficulty + tier_term

    # Cover: one COUNT over this round's COVER declarations targeting the fleer.
    cover_count = CombatRoundAction.objects.filter(
        participant__encounter=encounter,
        participant__status=ParticipantStatus.ACTIVE,
        round_number=action.round_number,
        maneuver=CombatManeuver.COVER,
        focused_ally_target=participant,
    ).count()

    # Route the cover bonus through the shared modifier seam (the same idiom
    # as effort in CombatTechniqueResolver._roll_check) so the recorded
    # provenance carries a labeled "covering allies" contribution.
    extra_contributions: list[ModifierContribution] = []
    if cover_count:
        extra_contributions.append(
            ModifierContribution(
                source_kind=ModifierSourceKind.CHARACTER,
                source_label=f"Covering allies x{cover_count}",
                value=config.cover_bonus * cover_count,
            )
        )
    breakdown = collect_check_modifiers(
        participant.character_sheet,
        config.check_type,
        extra_contributions=extra_contributions,
    )

    consequences = (
        resolve_pool_consequences(config.consequence_pool)
        if config.consequence_pool_id is not None
        else []
    )
    character = participant.character_sheet.character
    pending = select_consequence(
        character,
        config.check_type,
        difficulty,
        consequences,
        extra_modifiers=breakdown.total,
    )

    success_level = pending.check_result.success_level
    escaped = success_level >= FLEE_PARTIAL_SUCCESS_LEVEL
    consequence_applies = success_level <= FLEE_PARTIAL_SUCCESS_LEVEL

    if escaped:
        participant.status = ParticipantStatus.FLED
        participant.save(update_fields=["status"])

        # Combat-owned engagement teardown on successful flee (#872).
        from world.mechanics.constants import EngagementType  # noqa: PLC0415
        from world.mechanics.services import end_engagement  # noqa: PLC0415

        end_engagement(
            participant.character_sheet.character,
            EngagementType.COMBAT,
            source=participant.encounter,
        )

    # ACTION-mode Interaction anchor + live broadcast (mirrors the tail of
    # _resolve_pc_action).
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        create_action_interaction,
        render_flee_outcome_narration,
    )
    from world.scenes.interaction_services import push_interaction  # noqa: PLC0415

    interaction = create_action_interaction(
        participant=participant,
        round_number=action.round_number,
        summary_label="Flee",
    )
    if interaction is not None:
        action.interaction = interaction
        action.interaction_timestamp = interaction.timestamp
        action.save(update_fields=["interaction", "interaction_timestamp"])
        push_interaction(interaction)

    if consequence_applies and config.consequence_pool_id is not None:
        apply_resolution(pending, ResolutionContext(character=character))
        _record_combat_consequence(
            participant.character_sheet,
            config.check_type,
            config.consequence_pool,
            pending,
            breakdown,
            interaction=interaction,
            summary="flee attempt",
        )

    narration = render_flee_outcome_narration(
        actor_label=str(participant),
        escaped=escaped,
        at_cost=escaped and consequence_applies,
    )
    broadcast_action_outcome(encounter=encounter, narration=narration)

    return outcome


def _resolve_pc_action(
    participant: CombatParticipant,
    action: CombatRoundAction,
    offense_check_fn: PerformCheckFn | None = None,
) -> ActionOutcome:
    """Resolve a single PC's focused action during round resolution.

    For non-combo actions, derives the offense_check_type from the declared
    technique's action_template. The check result's success_level scales damage:
    - success_level >= 2: full base_power
    - success_level == 1: half base_power
    - success_level <= 0: zero (miss)

    Raises ActionDispatchError(TECHNIQUE_NOT_COMBAT_READY) if the technique has
    no action_template (i.e. it has not been configured for combat use).

    Fatigue is applied after the action resolves (both combo and non-combo).
    """
    # Flee resolves as its own graded check (#878). COVER deliberately falls
    # through to the passives-only early return below — its effect is the
    # cover_bonus it contributes to the ally's flee check.
    if action.maneuver == CombatManeuver.FLEE:
        return _resolve_flee(participant, action)

    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))

    technique = action.focused_action
    if technique is None:
        # Passives-only round (e.g. flee) — no focused action to resolve.
        return outcome

    target = action.focused_opponent_target
    fatigue_category = action.focused_category or ActionCategory.PHYSICAL

    # combat_result is only set on non-combo magic-pipeline paths; all other
    # branches (combos, passives-only) produce no CombatTechniqueResult.
    combat_result: CombatTechniqueResult | None = None

    # Combo upgrades require an active opponent target — bail out early if defeated.
    if target is not None and action.combo_upgrade:
        target.refresh_from_db()
        if target.status != OpponentStatus.DEFEATED:
            combo = action.combo_upgrade
            dmg_result = apply_damage_to_opponent(
                target,
                combo.bonus_damage,
                bypass_soak=combo.bypass_soak,
                source_sheet=participant.character_sheet,
            )
            outcome.combo_used = combo
            outcome.damage_results.append(dmg_result)
    elif not action.combo_upgrade:
        # All non-combo techniques (damage AND non-attack) route through the magic
        # pipeline. The resolver internally handles damage (if base_power) and
        # conditions (if condition_applications rows exist).
        template = technique.action_template
        if template is None:
            raise ActionDispatchError(ActionDispatchError.TECHNIQUE_NOT_COMBAT_READY)
        combat_result = resolve_combat_technique(
            participant=participant,
            action=action,
            fatigue_category=fatigue_category,
            offense_check_type=template.check_type,
            offense_check_fn=offense_check_fn,
        )
        outcome.damage_results.extend(combat_result.damage_results)

    # Apply fatigue after action resolves
    apply_fatigue(
        participant.character_sheet,
        fatigue_category,
        technique.anima_cost,
        action.effort_level,
    )

    # Create the ACTION-mode Interaction, link it, and broadcast it live.
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        create_action_interaction,
        render_action_declaration_label,
        render_action_outcome_narration,
    )
    from world.scenes.interaction_services import push_interaction  # noqa: PLC0415

    interaction = create_action_interaction(
        participant=participant,
        round_number=action.round_number,
        summary_label=render_action_declaration_label(action),
    )
    if interaction is not None:
        action.interaction = interaction
        action.interaction_timestamp = interaction.timestamp
        action.save(update_fields=["interaction", "interaction_timestamp"])
        push_interaction(interaction)
        if combat_result is not None:
            from world.scenes.power_ledger_services import persist_power_ledger  # noqa: PLC0415

            persist_power_ledger(interaction=interaction, ledger=combat_result.power_ledger)

    # Broadcast a durable, Narrator-authored OUTCOME line for this action.
    # The power_ledger is threaded from the combat resolver (magic pipeline) so
    # narration can fold in ward/environment drama clauses. Combo paths and
    # unconfirmed casts produce no ledger (combat_result is None).
    target_label = target.name if target is not None else None
    narration = render_action_outcome_narration(
        actor_label=str(participant),
        technique_name=technique.name,
        target_label=target_label,
        outcome=outcome,
        power_ledger=combat_result.power_ledger if combat_result is not None else None,
    )
    broadcast_action_outcome(encounter=participant.encounter, narration=narration)

    return outcome


def _resolve_npc_action(
    opponent: CombatOpponent,
    npc_action: CombatOpponentAction,
    defense_check_type: CheckType | None,
    defense_check_fn: PerformCheckFn | None,
) -> ActionOutcome:
    """Resolve a single NPC's action against targeted PCs.

    After applying damage, processes knockout/death transitions and
    applies any conditions from the threat entry to damaged targets.
    """
    outcome = ActionOutcome(entity_type=ENTITY_TYPE_NPC, entity_label=str(opponent))

    try:
        targets: list[CombatParticipant] = npc_action.cached_targets
    except AttributeError:
        targets = list(npc_action.targets.all())

    # Pre-fetch conditions from the threat entry
    try:
        conditions = npc_action.threat_entry.cached_conditions
    except AttributeError:
        conditions = list(npc_action.threat_entry.conditions_applied.all())

    # One ACTION-mode Interaction anchors every survivability ConsequenceOutcome
    # this NPC action drives (#850). Authored by the Narrator persona because the
    # NPC opponent has no PRIMARY persona.
    from world.combat.interaction_services import (  # noqa: PLC0415
        create_npc_action_interaction,
    )
    from world.vitals.services import is_dead  # noqa: PLC0415

    npc_action_label = ", ".join(str(t) for t in targets) if targets else None
    npc_action_interaction = create_npc_action_interaction(
        opponent_action=npc_action,
        target_label=npc_action_label,
    )

    condition_applications: list[tuple[ObjectDB, ConditionTemplate]] = []

    for target_participant in targets:
        # A successful escape protects for the rest of the round (#878). The
        # idmapper guarantees this is the same instance _resolve_flee just
        # mutated, so the status write is visible without a re-fetch.
        if target_participant.status != ParticipantStatus.ACTIVE:
            continue

        # Damage recipients: any not-dead target is valid. Unconscious / dying
        # PCs still take damage (incapacitation/dying are conditions, not a gate
        # on damage application). Only the dead are excluded.
        if is_dead(target_participant.character_sheet):
            continue

        if defense_check_type is not None:
            defense = resolve_npc_attack(
                npc_action,
                target_participant,
                defense_check_type,
                perform_check_fn=defense_check_fn,
            )
            dmg_result = defense.damage_result
        else:
            dmg_result = apply_damage_to_participant(
                target_participant,
                npc_action.threat_entry.base_damage,
                damage_type=npc_action.threat_entry.damage_type,
                source=opponent,
            )
        outcome.damage_results.append(dmg_result)

        # Survivability pipeline — knockout, death, wound checks
        from world.vitals.services import process_damage_consequences  # noqa: PLC0415

        consequence = process_damage_consequences(
            character_sheet=target_participant.character_sheet,
            damage_dealt=dmg_result.damage_dealt,
            damage_type=npc_action.threat_entry.damage_type,
            combat_interaction=npc_action_interaction,
        )
        outcome.damage_consequences.append(consequence)

        # Collect condition applications for bulk apply
        if dmg_result.damage_dealt > 0 and conditions:
            target_obj = target_participant.character_sheet.character
            condition_applications.extend((target_obj, ct) for ct in conditions)

    # Bulk-apply all conditions from this NPC action
    if condition_applications:
        from world.conditions.services import bulk_apply_conditions  # noqa: PLC0415
        from world.conditions.types import BulkConditionApplication  # noqa: PLC0415

        bulk_apply_conditions(
            [BulkConditionApplication(target=t, template=ct) for (t, ct) in condition_applications]
        )

    # Broadcast a durable, Narrator-authored OUTCOME line for the NPC action.
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        render_action_outcome_narration,
    )

    npc_target_label = ", ".join(str(t) for t in targets) if targets else None
    npc_narration = render_action_outcome_narration(
        actor_label=str(opponent),
        technique_name=npc_action.threat_entry.name,
        target_label=npc_target_label,
        outcome=outcome,
    )
    broadcast_action_outcome(encounter=opponent.encounter, narration=npc_narration)

    return outcome


def _resolve_actions(  # noqa: PLR0913 - resolution needs all check params
    resolution_order: list[tuple[str, CombatParticipant | CombatOpponent]],
    pc_actions: dict[int, CombatRoundAction],
    npc_actions: dict[int, list[CombatOpponentAction]],
    defense_check_type: CheckType | None,
    defense_check_fn: PerformCheckFn | None,
    offense_check_fn: PerformCheckFn | None,
) -> list[ActionOutcome]:
    """Iterate resolution order and resolve each entity's action."""
    outcomes: list[ActionOutcome] = []
    for entity_type, entity in resolution_order:
        if entity_type == ENTITY_TYPE_PC:
            if not isinstance(entity, CombatParticipant):
                continue
            action = pc_actions.get(entity.pk)
            if action is not None:
                outcomes.append(_resolve_pc_action(entity, action, offense_check_fn))

        elif entity_type == ENTITY_TYPE_NPC:
            if not isinstance(entity, CombatOpponent):
                continue
            outcomes.extend(
                _resolve_npc_action(entity, npc_action, defense_check_type, defense_check_fn)
                for npc_action in npc_actions.get(entity.pk, [])
            )
    return outcomes


def _check_boss_transitions(
    encounter: CombatEncounter,
) -> list[tuple[CombatOpponent, int]]:
    """Check all active bosses for phase transitions, return transitions."""
    transitions: list[tuple[CombatOpponent, int]] = []
    boss_opponents = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
            tier=OpponentTier.BOSS,
        )
    )
    for boss in boss_opponents:
        boss.refresh_from_db()
        new_phase = check_and_advance_boss_phase(boss)
        if new_phase is not None:
            transitions.append((boss, new_phase.phase_number))
    return transitions


def cleanup_completed_encounter(encounter: CombatEncounter) -> None:
    """Delete encounter-ephemeral CombatNPC ObjectDBs. Persistent NPCs and PCs
    are never touched. Layer 5 of the multi-layer guard: defensive re-check
    before each delete in case a corrupt row escaped Layers 1–4.

    CombatOpponent rows are preserved (historical record). Only the ephemeral
    ObjectDB is destroyed; the SET_NULL FK behavior nulls
    CombatOpponent.objectdb after deletion.
    """
    # Sweep covenant rite buffs for this encounter (stamps completed_at on the
    # rite instances in addition to removing their granted condition).
    from world.covenants.services import complete_rites_for_encounter  # noqa: PLC0415

    complete_rites_for_encounter(encounter=encounter)

    # Generically expire any remaining UNTIL_END_OF_COMBAT conditions on the
    # encounter's participants and opponents. The rite sweep above already
    # removed its own (rite-granted) buffs, so this is idempotent for those;
    # it catches every other end-of-combat condition (e.g. technique-applied)
    # that nothing else expires. Runs before ephemeral NPC deletion so the
    # sweep observes those targets too.
    from world.conditions.services import expire_end_of_combat_conditions  # noqa: PLC0415

    participant_targets = [
        p.character_sheet.character
        for p in CombatParticipant.objects.filter(encounter=encounter).select_related(
            "character_sheet__character"
        )
    ]
    opponent_targets = [
        opp.objectdb
        for opp in CombatOpponent.objects.filter(encounter=encounter).select_related("objectdb")
    ]

    # End Audere and Audere Majora BEFORE the generic condition sweep (#873, #543):
    # the sweep would strip the condition without reverting the engagement intensity
    # modifier or anima-pool expansion — only end_audere reverts those. Also delete
    # any unanswered pending offers; the gate dies with the encounter.
    #
    # Note: end_audere reverts intensity modifier + anima-pool expansion;
    # end_audere_majora only removes the condition (no modifier reversal needed).
    # The loop preserves this by calling the per-kind end_fn as-is.
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.magic.audere import (  # noqa: PLC0415
        AUDERE_CONDITION_NAME,
        AUDERE_MAJORA_CONDITION_NAME,
        PendingAudereOffer,
        end_audere,
    )
    from world.magic.audere_majora import (  # noqa: PLC0415
        PendingAudereMajoraOffer,
        end_audere_majora,
    )

    for condition_name, end_fn, pending_offer_model in [
        (AUDERE_CONDITION_NAME, end_audere, PendingAudereOffer),
        (AUDERE_MAJORA_CONDITION_NAME, end_audere_majora, PendingAudereMajoraOffer),
    ]:
        target_ids = set(
            ConditionInstance.objects.filter(
                target__in=participant_targets,
                condition__name=condition_name,
            ).values_list("target_id", flat=True)
        )
        for target in participant_targets:
            if target.pk in target_ids:
                end_fn(target)
        pending_offer_model.objects.filter(
            character_sheet__character__in=participant_targets
        ).delete()

    expire_end_of_combat_conditions(participant_targets + opponent_targets)

    # Combat-owned engagement teardown (#872): deleting the engagement discards
    # the transient escalation process modifiers. Must run AFTER end_audere
    # (which subtracts its own bonus from the row first — see comment above).
    from world.mechanics.constants import EngagementType  # noqa: PLC0415
    from world.mechanics.services import end_engagement  # noqa: PLC0415

    for target in participant_targets:
        end_engagement(target, EngagementType.COMBAT, source=encounter)

    # Escalation room-trigger teardown (#872): drop the spike triggers unless
    # another live escalating encounter still shares the room.
    from world.combat.escalation import remove_escalation_room_triggers  # noqa: PLC0415

    remove_escalation_room_triggers(encounter)

    qs = CombatOpponent.objects.filter(
        encounter=encounter,
        objectdb_is_ephemeral=True,
    ).select_related("objectdb")
    for opp in qs:
        objectdb = opp.objectdb
        if objectdb is None:
            continue
        if not is_combat_npc_typeclass(objectdb):
            logger.error(
                "Refusing to delete: %s is not a CombatNPC typeclass",
                objectdb,
            )
            continue
        if has_persistent_identity_references(objectdb):
            logger.error(
                "Refusing to delete: %s has persistent identity references",
                objectdb,
            )
            continue
        objectdb.delete()


def _check_encounter_completion(encounter: CombatEncounter) -> bool:
    """Return True if the encounter should be marked complete.

    Complete when either side is wiped: all opponents defeated, OR every active
    PC is "down" (cannot act — dead or incapacitated). A dying-but-conscious PC
    can still act, so the encounter is not lost while any PC can_act.
    """
    from world.vitals.services import can_act  # noqa: PLC0415

    all_opponents_down = not CombatOpponent.objects.filter(
        encounter=encounter,
        status=OpponentStatus.ACTIVE,
    ).exists()

    active_participants = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).select_related("character_sheet__character")

    all_pcs_down = not any(can_act(p.character_sheet) for p in active_participants)

    return all_opponents_down or all_pcs_down


def _classify_encounter_outcome(encounter: CombatEncounter) -> EncounterOutcome:
    """Classify a completing encounter (#876 spec §1).

    1. No ACTIVE opponents and no Hero Killer present → VICTORY. An unbeatable
       Hero Killer (#875) on the field at any status forbids VICTORY.
    2. No ACTIVE participants and at least one FLED → FLED.
    3. Else → DEFEAT (catch-all: downed ACTIVE participants, or all-REMOVED).
    """
    any_active_opponents = CombatOpponent.objects.filter(
        encounter=encounter, status=OpponentStatus.ACTIVE
    ).exists()
    if not any_active_opponents:
        hero_killer_present = CombatOpponent.objects.filter(
            encounter=encounter, tier=OpponentTier.HERO_KILLER
        ).exists()
        if not hero_killer_present:
            return EncounterOutcome.VICTORY
        # An unbeatable Hero Killer was on the field -- never a victory.
        # Fall through to FLED / DEFEAT classification below.

    statuses = set(
        CombatParticipant.objects.filter(encounter=encounter).values_list("status", flat=True)
    )
    no_active = ParticipantStatus.ACTIVE not in statuses
    if no_active and ParticipantStatus.FLED in statuses:
        return EncounterOutcome.FLED
    return EncounterOutcome.DEFEAT


@transaction.atomic
def complete_encounter(encounter: CombatEncounter, *, outcome: EncounterOutcome) -> None:
    """Single completion seam for round resolution and the GM end endpoint (#876).

    Order: persist flip → Narrator OUTCOME interaction → aftermath (anchored to
    that interaction, before ephemeral-NPC cleanup) → counters → completion
    event → cleanup. ABANDONED is administrative closure: skips aftermath and
    counters but still narrates, emits, and cleans up.

    Atomic so a bare caller (the GM end endpoint) cannot strand a COMPLETED
    flip with the aftermath/cleanup tail skipped — the double-completion guard
    would otherwise block any retry. Inside resolve_round it is a savepoint.
    """
    if encounter.status == EncounterStatus.COMPLETED:
        msg = f"Encounter {encounter.pk} is already completed."
        raise ValueError(msg)

    encounter.status = EncounterStatus.COMPLETED
    encounter.outcome = outcome
    encounter.completed_at = timezone.now()
    encounter.save(update_fields=["status", "outcome", "completed_at"])

    interaction = _broadcast_encounter_outcome(encounter, outcome)

    if outcome != EncounterOutcome.ABANDONED:
        _apply_aftermath_rules(encounter, outcome, interaction)
        _apply_opponent_aftermath_pools(encounter, outcome)
        _increment_completion_counters(encounter, outcome)

    _emit_encounter_completed(encounter, outcome)
    cleanup_completed_encounter(encounter)


def end_encounter(encounter: CombatEncounter) -> CombatEncounter:
    """GM force-end: completes as ABANDONED (#876 §8) — the sole ABANDONED producer."""
    complete_encounter(encounter, outcome=EncounterOutcome.ABANDONED)
    return encounter


def _broadcast_encounter_outcome(
    encounter: CombatEncounter, outcome: EncounterOutcome
) -> Interaction | None:
    """Assemble side labels and persist+broadcast the ceremonial OUTCOME line."""
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        render_encounter_outcome_narration,
    )

    participants = list(
        CombatParticipant.objects.filter(encounter=encounter).select_related(
            "character_sheet__character"
        )
    )
    opponents = list(CombatOpponent.objects.filter(encounter=encounter))
    narration = render_encounter_outcome_narration(
        outcome=outcome,
        active_labels=[str(p) for p in participants if p.status == ParticipantStatus.ACTIVE],
        fled_labels=[str(p) for p in participants if p.status == ParticipantStatus.FLED],
        defeated_opponent_labels=[o.name for o in opponents if o.status == OpponentStatus.DEFEATED],
    )
    return broadcast_action_outcome(encounter=encounter, narration=narration)


def _apply_aftermath_rules(
    encounter: CombatEncounter,
    outcome: EncounterOutcome,
    interaction: Interaction | None,
) -> None:
    """Per-PC graded aftermath via the authored (outcome, risk) cell (#876 §3).

    Mirrors _resolve_flee's pipeline: modifiers → select_consequence (theater
    included) → apply_resolution → record_consequence_outcome anchored to the
    encounter OUTCOME interaction. Legend, when authored, rides LEGEND_AWARD
    consequences in the pool — context.participants carries the PC's persona.
    """
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_resolution,
        resolve_pool_consequences,
        select_consequence,
    )
    from world.checks.types import ResolutionContext  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    rule = (
        EncounterAftermathRule.objects.filter(outcome=outcome, risk_level=encounter.risk_level)
        .select_related("check_type", "consequence_pool")
        .first()
    )
    if rule is None or rule.consequence_pool_id is None:
        return

    affected_status = (
        ParticipantStatus.FLED if outcome == EncounterOutcome.FLED else ParticipantStatus.ACTIVE
    )
    affected = list(
        CombatParticipant.objects.filter(
            encounter=encounter, status=affected_status
        ).select_related("character_sheet__character")
    )
    consequences = resolve_pool_consequences(rule.consequence_pool)

    for participant in affected:
        sheet = participant.character_sheet
        character = sheet.character
        breakdown = collect_check_modifiers(sheet, rule.check_type)
        pending = select_consequence(
            character,
            rule.check_type,
            rule.base_difficulty,
            consequences,
            extra_modifiers=breakdown.total,
        )
        try:
            participants_ctx = [sheet.primary_persona]
        except Persona.DoesNotExist:
            participants_ctx = None
        apply_resolution(
            pending,
            ResolutionContext(
                character=character,
                scene=encounter.scene,
                participants=participants_ctx,
            ),
        )
        _record_combat_consequence(
            sheet,
            rule.check_type,
            rule.consequence_pool,
            pending,
            breakdown,
            interaction=interaction,
            summary=f"encounter aftermath ({outcome.label})",
        )


def _apply_opponent_aftermath_pools(encounter: CombatEncounter, outcome: EncounterOutcome) -> None:
    """Fire each DEFEATED opponent's authored aftermath pool on PC victory (#876 §4).

    Deterministic (story-consequence semantics, like beat pools). Context follows
    the beats GLOBAL idiom: the opponent's ObjectDB when set, else an unsaved
    stub that is only identity-safe for non-character effects.
    """
    if outcome != EncounterOutcome.VICTORY:
        return

    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_pool_deterministically,
    )
    from world.checks.types import ResolutionContext  # noqa: PLC0415

    qs = CombatOpponent.objects.filter(
        encounter=encounter,
        status=OpponentStatus.DEFEATED,
        aftermath_pool__isnull=False,
    ).select_related("aftermath_pool", "objectdb")
    for opponent in qs:
        character = opponent.objectdb or ObjectDB()  # unsaved stub — non-character effects only
        apply_pool_deterministically(
            pool=opponent.aftermath_pool,
            context=ResolutionContext(character=character, scene=encounter.scene),
        )


def _increment_completion_counters(encounter: CombatEncounter, outcome: EncounterOutcome) -> None:
    """encounters_won / encounters_lost / encounters_fled aggregates (#876 §7)."""
    from world.combat.achievement_counters import (  # noqa: PLC0415
        STAT_KEY_ENCOUNTERS_FLED,
        STAT_KEY_ENCOUNTERS_LOST,
        STAT_KEY_ENCOUNTERS_WON,
        increment_combat_counter,
    )

    outcome_key = {
        EncounterOutcome.VICTORY: STAT_KEY_ENCOUNTERS_WON,
        EncounterOutcome.DEFEAT: STAT_KEY_ENCOUNTERS_LOST,
    }.get(outcome)

    participants = CombatParticipant.objects.filter(encounter=encounter).select_related(
        "character_sheet"
    )
    for participant in participants:
        if participant.status == ParticipantStatus.FLED:
            increment_combat_counter(participant.character_sheet, STAT_KEY_ENCOUNTERS_FLED)
        elif participant.status == ParticipantStatus.ACTIVE and outcome_key is not None:
            increment_combat_counter(participant.character_sheet, outcome_key)


def _emit_encounter_completed(encounter: CombatEncounter, outcome: EncounterOutcome) -> None:
    """Emit the ENCOUNTER_COMPLETED reactive hook (#876 §6).

    Downstream systems — stories, missions, achievements, Legend — subscribe
    via triggers. Never XP: combat does not award XP. Skips when no room
    (emit_event requires a location); mirrors the _emit_death_gate idiom.
    """
    room = encounter.room
    if room is None:
        logger.debug(
            "Encounter %s completed with no room; skipping ENCOUNTER_COMPLETED emit.",
            encounter.pk,
        )
        return
    emit_event(
        EventName.ENCOUNTER_COMPLETED,
        EncounterCompletedPayload(
            encounter=encounter,
            outcome=str(outcome),
            scene=encounter.scene,
            room=room,
        ),
        location=room,
    )


def _resolve_declared_challenges(
    encounter: CombatEncounter,
    round_number: int,
    resolution_order: list[tuple[str, CombatParticipant | CombatOpponent]],
) -> list[ChallengeResolutionResult]:
    """Post-pass: resolve RoundChallengeDeclarations in participant initiative order.

    Called after all combat-action resolution for the round.  Fetches bridge rows,
    orders them to match the existing resolution_order for PC participants, resolves
    each character's declared challenge (re-validating eligibility via
    get_available_actions), and deletes all bridge rows for the round.

    Ineligible-skip: if get_available_actions returns no action matching the
    declared (challenge_instance_id, approach_id), the declaration is silently
    skipped — no CharacterChallengeRecord is created and no exception is raised.
    This mirrors dispatch-time security: declared state may be stale if a
    character lost their capability between declaration and resolution.

    The delete of bridge rows runs inside the caller's @transaction.atomic so it
    is consistent with the rest of round resolution.
    """
    declarations = list(
        RoundChallengeDeclaration.objects.filter(
            encounter=encounter,
            round_number=round_number,
        ).select_related(
            "participant",
            "participant__character_sheet",
            "challenge_instance",
            "challenge_instance__location",
            "challenge_approach",
        )
    )

    if not declarations:
        return []

    # Build participant_id → declaration map for O(n) ordering.
    decl_by_participant: dict[int, RoundChallengeDeclaration] = {
        d.participant_id: d for d in declarations
    }

    # Order by the same resolution_order combat uses for PC participants.
    # NPCs never declare challenges, so only ENTITY_TYPE_PC entries matter.
    ordered: list[RoundChallengeDeclaration] = []
    for entity_type, entity in resolution_order:
        if entity_type != ENTITY_TYPE_PC:
            continue
        if not isinstance(entity, CombatParticipant):
            continue
        decl = decl_by_participant.pop(entity.pk, None)
        if decl is not None:
            ordered.append(decl)

    # Any declarations for participants not in resolution_order (e.g. DYING without
    # final-round) come after, preserving their insertion order.
    ordered.extend(decl_by_participant.values())

    outcomes: list[ChallengeResolutionResult] = []
    for decl in ordered:
        character = decl.participant.character_sheet.character
        challenge_instance = decl.challenge_instance
        approach = decl.challenge_approach
        location = challenge_instance.location

        # Re-validate eligibility: character must still have a matching AvailableAction.
        available_actions = get_available_actions(character, location)
        matching = next(
            (
                a
                for a in available_actions
                if a.challenge_instance_id == challenge_instance.pk and a.approach_id == approach.pk
            ),
            None,
        )
        if matching is None:
            logger.warning(
                "Skipping deferred challenge declaration for participant %s "
                "(challenge_instance=%s, approach=%s): "
                "no matching AvailableAction at resolution time.",
                decl.participant_id,
                challenge_instance.pk,
                approach.pk,
            )
            continue

        outcome = resolve_challenge(
            character,
            challenge_instance,
            approach,
            matching.capability_source,
        )
        outcomes.append(outcome)

        # Broadcast a durable, Narrator-authored OUTCOME line for this challenge,
        # mirroring the per-action broadcast in _resolve_pc_action (#644).
        from world.combat.interaction_services import (  # noqa: PLC0415
            broadcast_action_outcome,
            render_challenge_outcome_narration,
        )

        narration = render_challenge_outcome_narration(
            actor_label=str(decl.participant),
            challenge_name=outcome.challenge_name,
            approach_name=outcome.approach_name,
            outcome_label=outcome.check_result.outcome_name,
            success_level=outcome.check_result.success_level,
        )
        broadcast_action_outcome(encounter=encounter, narration=narration)

    # Delete all bridge rows for this round inside the outer atomic block.
    RoundChallengeDeclaration.objects.filter(
        encounter=encounter,
        round_number=round_number,
    ).delete()

    return outcomes


def _resolve_clashes(
    encounter: CombatEncounter,
    round_number: int,
    resolution_order: list[tuple[str, CombatParticipant | CombatOpponent]],  # noqa: ARG001
) -> list[ClashRoundResult]:
    """Post-pass: detect clash opportunities, then drive one round per active Clash.

    Called after all combat-action resolution for the round.  Two phases:

    1. **Opportunity detection** — ``detect_clash_opportunities`` inspects the
       round's declared PC + NPC actions and creates ``Clash`` rows for newly-
       emerged opportunities.  Newly-created clashes participate in the same
       round's post-pass so that the first round of a clash is resolved
       immediately.

    2. **Per-clash round driver** — for each ACTIVE Clash (including any just
       created in step 1), gather the PC's ``ClashContributionDeclaration`` rows,
       build ``PreparedClashContribution`` objects, and call ``run_clash_round``.
       Clashes are iterated in ``Clash.pk`` order for deterministic resolution.

       TODO(Phase 5 / initiative ordering): order PC-initiated clashes by the
       initiating participant's initiative slot, mirroring how
       ``_resolve_declared_challenges`` follows ``resolution_order``.  NPC-initiated
       clashes (WARD, LOCK/ESCAPING) don't have a PC initiator in the same sense;
       they can resolve at a fixed NPC slot or after all PC-initiated clashes.
       For v1, pk order is sufficient and deterministic.

    3. **Declaration cleanup** — all ``ClashContributionDeclaration`` rows for
       this round are deleted atomically after all clashes are processed, inside
       the caller's ``@transaction.atomic`` block.

    ``npc_attack_affinity`` is resolved at post-pass time from
    ``clash.triggering_threat_entry``.  ``ThreatPoolEntry`` has no affinity field
    (confirmed in Task 5.3 investigation) — ``npc_attack_affinity`` is always
    ``None`` in v1, so ``affinity_tilt`` always returns 0.  When a future task
    adds an affinity field to ``ThreatPoolEntry``, update this function to read it.

    Runs inside the outer ``@transaction.atomic`` on ``resolve_round`` — no
    separate ``@transaction.atomic`` decorator is needed here.

    Args:
        encounter: The active ``CombatEncounter`` being resolved.
        round_number: The current encounter round number (1-indexed).
        resolution_order: PC/NPC action resolution order (reserved for future
            initiative-based clash ordering; unused in v1).

    Returns:
        A list of ``ClashRoundResult`` objects, one per Clash that was driven
        this round.  May be empty when no Clashes are active.
    """
    from world.combat.clash import (  # noqa: PLC0415
        detect_clash_opportunities,
        run_clash_round,
    )
    from world.combat.constants import ClashStatus  # noqa: PLC0415

    # 1. Detect new opportunities this round (creates Clash rows).
    detect_clash_opportunities(encounter=encounter, round_number=round_number)

    # 2. Find all ACTIVE clashes (includes any just created in step 1).
    # TODO(Phase 5 / initiative ordering): order by initiating participant's
    # initiative slot instead of pk for PC-initiated clashes.
    active_clashes = list(
        Clash.objects.filter(
            encounter=encounter,
            status=ClashStatus.ACTIVE,
        ).select_related("npc_opponent", "triggering_threat_entry")
    )

    if not active_clashes:
        return []

    # 3. Gather all declarations for this round and group by clash_id.
    declarations = list(
        ClashContributionDeclaration.objects.filter(
            encounter=encounter,
            round_number=round_number,
        ).select_related(
            "clash",
            "participant__character_sheet",
            "technique",
            "technique__action_template",
        )
    )
    decls_by_clash: dict[int, list[ClashContributionDeclaration]] = defaultdict(list)
    for decl in declarations:
        decls_by_clash[decl.clash_id].append(decl)

    # 4. Load configs once (singleton reads; SharedMemoryModel caches them).
    # get_clash_config / get_strain_config are defined later in this module;
    # Python resolves names at call time so the forward reference is fine.
    config_clash = get_clash_config()
    config_strain = get_strain_config()

    # 5. Drive one round per active clash.
    outcomes: list[ClashRoundResult] = []
    for clash in active_clashes:
        clash_decls = decls_by_clash.get(clash.pk, [])

        # Build PreparedClashContribution objects for this clash's declarations.
        # npc_attack_affinity: ThreatPoolEntry has no affinity field in v1 — pass None.
        # When a future task adds an affinity field, read it here from
        # clash.triggering_threat_entry.
        pc_contributions: list[PreparedClashContribution] = [
            PreparedClashContribution(
                character_sheet=decl.participant.character_sheet,
                action_slot=decl.action_slot,
                technique=decl.technique,
                strain_commitment=decl.strain_commitment,
                npc_attack_affinity=None,  # ThreatPoolEntry has no affinity field in v1
            )
            for decl in clash_decls
        ]

        result = run_clash_round(
            clash=clash,
            round_number=round_number,
            pc_contributions=pc_contributions,
            config_clash=config_clash,
            config_strain=config_strain,
        )
        outcomes.append(result)

        # When the clash resolved this round, broadcast a durable, Narrator-
        # authored OUTCOME line for the break/lock/ward result (#644). Mirrors
        # the per-action broadcast in _resolve_pc_action.
        if result.resolution is not None:
            from world.combat.interaction_services import (  # noqa: PLC0415
                broadcast_action_outcome,
                render_clash_outcome_narration,
            )

            opponent_label = clash.npc_opponent.name if clash.npc_opponent_id else "?"
            consequence = result.resolution.consequence_applied
            narration = render_clash_outcome_narration(
                flavor_label=clash.get_flavor_display(),
                opponent_label=opponent_label,
                resolution_tier=result.resolution.resolution,
                consequence_label=consequence.label if consequence is not None else None,
            )
            broadcast_action_outcome(encounter=encounter, narration=narration)

    # 6. Delete all declarations for this round (inside caller's atomic block).
    ClashContributionDeclaration.objects.filter(
        encounter=encounter,
        round_number=round_number,
    ).delete()

    return outcomes


@transaction.atomic
def resolve_round(
    encounter: CombatEncounter,
    *,
    defense_check_fn: PerformCheckFn | None = None,
    defense_check_type: CheckType | None = None,
    offense_check_fn: PerformCheckFn | None = None,
) -> RoundResolutionResult:
    """Orchestrate a full combat round: detect combos -> resolve -> consequences.

    High-level flow:
    1. Validate encounter is in ``DECLARING`` status, transition to ``RESOLVING``.
    2. Detect available combos from declared actions. Note: combo upgrades must
       happen during DECLARING phase via ``upgrade_action_to_combo``. The
       detection here is informational — it reports what combos were available
       and which actions were upgraded (``combo_upgrade != null``).
    3. Iterate resolution order (speed-rank sorted PCs and NPCs).
       - For each **PC**: resolve focused action against target opponent.
         If the action has a ``combo_upgrade``, apply bonus damage with soak
         bypass. Otherwise derive the offense_check_type from the declared
         technique's action_template and route through resolve_combat_technique.
         Apply fatigue after each action.
       - For each **NPC**: resolve each targeted PC's defensive check.
         Process knockout/death transitions and apply conditions.
    4. Post-pass: resolve deferred RoundChallengeDeclarations in initiative
       order (reusing the round's resolution_order). Each participant's
       eligibility is re-validated via get_available_actions; ineligible
       declarations are skipped. Bridge rows for the round are deleted inside
       the same atomic block. Resolved outcomes populate ``challenge_outcomes``
       on the return value.
    4b. Post-pass: resolve clashes — detect new clash opportunities from the
       round's declared PC + NPC actions (creates Clash rows), then drive one
       round per active Clash. Gather ClashContributionDeclaration rows,
       build PreparedClashContribution objects, and call run_clash_round for
       each. Clean up all declarations for the round. Clash round outcomes
       populate ``clash_outcomes`` on the return value.
    5. Advance bleed-out: each participant with an active Bleeding-Out condition
       rolls its stage resist check; terminal-stage failure marks life_state=DEAD.
    6. After all actions: check boss phase transitions for boss-tier opponents.
    7. Check encounter completion (all opponents defeated or all PCs down).
    8. Transition encounter to ``BETWEEN_ROUNDS`` or ``COMPLETED``.

    Args:
        encounter: The combat encounter to resolve.
        defense_check_fn: Optional ``perform_check`` override for PC defense.
        defense_check_type: The CheckType used for defensive rolls.
        offense_check_fn: Optional ``perform_check`` override for PC offense.
            The offense_check_type is now sourced from the declared technique's
            action_template.check_type — it is no longer passed externally.

    Returns:
        ``RoundResolutionResult`` with outcomes and phase transitions.
    """
    enc = CombatEncounter.objects.select_for_update().get(pk=encounter.pk)
    if enc.status != EncounterStatus.DECLARING:
        msg = (
            f"Cannot resolve round: encounter status is "
            f"'{enc.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    enc.status = EncounterStatus.RESOLVING
    enc.save(update_fields=["status"])

    round_number = enc.round_number
    result = RoundResolutionResult(round_number=round_number)

    # --- Combo detection (informational — upgrades happen in DECLARING) ---
    result.available_combos = detect_available_combos(encounter, round_number)

    # --- Build action lookups ---
    pc_actions: dict[int, CombatRoundAction] = {}
    for action in (
        CombatRoundAction.objects.filter(
            participant__encounter=encounter,
            round_number=round_number,
        )
        .select_related(
            "participant",
            "participant__character_sheet",
            "focused_action",
            "focused_action__effect_type",
            "focused_action__action_template",
            "focused_action__action_template__check_type",
            "focused_opponent_target",
            "combo_upgrade",
            "physical_passive",
            "social_passive",
            "mental_passive",
        )
        .prefetch_related(
            "physical_passive__condition_applications__condition",  # noqa: PREFETCH_STRING
            "social_passive__condition_applications__condition",  # noqa: PREFETCH_STRING
            "mental_passive__condition_applications__condition",  # noqa: PREFETCH_STRING
        )
    ):
        pc_actions[action.participant_id] = action

    npc_actions: dict[int, list[CombatOpponentAction]] = defaultdict(list)
    for npc_action in (
        CombatOpponentAction.objects.filter(
            opponent__encounter=encounter,
            round_number=round_number,
        )
        .select_related("opponent", "threat_entry")
        .prefetch_related(
            Prefetch(
                "targets",
                queryset=CombatParticipant.objects.select_related(
                    "character_sheet",
                ),
                to_attr="cached_targets",
            ),
            Prefetch(
                "threat_entry__conditions_applied",
                to_attr="cached_conditions",
            ),
        )
    ):
        npc_actions[npc_action.opponent_id].append(npc_action)

    # --- Resolve in speed-rank order ---
    resolution_order = get_resolution_order(encounter)
    _resolve_passive_actions(encounter, pc_actions)
    result.action_outcomes = _resolve_actions(
        resolution_order,
        pc_actions,
        npc_actions,
        defense_check_type,
        defense_check_fn,
        offense_check_fn,
    )

    # --- Post-pass: deferred challenge declarations (in initiative order) ---
    result.challenge_outcomes = _resolve_declared_challenges(
        encounter,
        round_number,
        resolution_order,
    )

    # --- Post-pass: clash opportunity detection + per-round drivers ---
    result.clash_outcomes = _resolve_clashes(
        encounter,
        round_number,
        resolution_order,
    )

    # --- Bleed-out progression ---
    # Each round, advance every participant's active Bleeding-Out condition.
    # advance_bleed_out rolls the stage resist check, advances on failure, and
    # marks life_state=DEAD at the terminal stage (closing the old divergence
    # where combat wrote status=DEAD but not life_state).
    from world.conditions.constants import (  # noqa: PLC0415
        BLEED_OUT_CONDITION_NAME,
    )
    from world.vitals.services import advance_bleed_out  # noqa: PLC0415

    # ConditionInstance.target → ObjectDB (related_name="condition_instances").
    bleeding_participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            character_sheet__character__condition_instances__condition__name=(
                BLEED_OUT_CONDITION_NAME
            ),
        )
        .select_related("character_sheet__character")
        .distinct()
    )
    for p in bleeding_participants:
        advance_bleed_out(p.character_sheet)

    # --- Round-tick: decrement rounds_remaining, tick DoT, fire expiry events ---
    from world.conditions.services import process_round_end  # noqa: PLC0415

    active_participants = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).select_related("character_sheet__character")
    for p in active_participants:
        process_round_end(p.character_sheet.character)

    active_opponents_end = CombatOpponent.objects.filter(
        encounter=encounter,
        status=OpponentStatus.ACTIVE,
    ).select_related("objectdb")
    for opp in active_opponents_end:
        if opp.objectdb is not None:
            process_round_end(opp.objectdb)

    # --- Boss phase transitions ---
    result.phase_transitions = _check_boss_transitions(encounter)

    # --- Check encounter completion ---
    if _check_encounter_completion(encounter):
        result.encounter_completed = True
        enc.round_started_at = None
        enc.save(update_fields=["round_started_at"])
        complete_encounter(enc, outcome=_classify_encounter_outcome(enc))
    else:
        # Note: round_number is NOT advanced here. begin_declaration_phase
        # handles incrementing round_number when transitioning from
        # BETWEEN_ROUNDS to DECLARING for the next round.
        enc.status = EncounterStatus.BETWEEN_ROUNDS
        enc.round_started_at = None
        enc.save(update_fields=["status", "round_started_at"])
    encounter.refresh_from_db()

    return result


# ---------------------------------------------------------------------------
# Clash tuning singleton accessors
# ---------------------------------------------------------------------------


def get_strain_config() -> StrainConfig:
    """Get-or-create the StrainConfig singleton (pk=1)."""
    from world.combat.models import (  # noqa: PLC0415
        StrainConfig,
    )

    cfg, _ = StrainConfig.objects.get_or_create(pk=1)
    return cfg


def get_clash_config() -> ClashConfig:
    """Get-or-create the ClashConfig singleton (pk=1)."""
    from world.combat.models import (  # noqa: PLC0415
        ClashConfig,
    )

    cfg, _ = ClashConfig.objects.get_or_create(pk=1)
    return cfg


# ---------------------------------------------------------------------------
# Player-facing clash contribution declaration (Task 7.1a)
# ---------------------------------------------------------------------------


@transaction.atomic
def declare_clash_contribution(
    *,
    participant: CombatParticipant,
    clash: Clash,
    action_slot: str,
    technique: Technique,
    strain_commitment: int,
) -> ClashContributionDeclaration:
    """Write (or overwrite) a PC's clash contribution declaration for the current round.

    Performs the atomic write.  All user-input validation lives in
    ``DeclareClashContributionSerializer`` — this function trusts its inputs and
    performs only defensive programmer-error assertions.

    The declaration is keyed on ``(encounter, round_number, participant, clash)``.
    Calling a second time in the same round replaces the prior declaration
    (idempotent re-declaration).

    Args:
        participant: The PC participant making the contribution.
        clash: The active ``Clash`` the contribution targets.
        action_slot: ``ClashActionSlot`` value (FOCUSED or PASSIVE).
        technique: The ``Technique`` the PC commits to the clash.
        strain_commitment: Extra anima committed on top of the technique cost floor.

    Returns:
        The created-or-updated ``ClashContributionDeclaration`` instance.

    Raises:
        ValueError: If ``clash.encounter`` does not match ``participant.encounter``
            (programmer error — the serializer enforces this for user input).
    """
    round_number = participant.encounter.round_number

    # Defensive assertion: catches programmer errors where the wrong clash or
    # participant is passed (the serializer already validates this for user input).
    if clash.encounter_id != participant.encounter_id:
        msg = (
            f"declare_clash_contribution: clash.encounter_id ({clash.encounter_id}) "
            f"does not match participant.encounter_id ({participant.encounter_id}). "
            "This is a programmer error — pass clashes and participants from the same encounter."
        )
        raise ValueError(msg)

    declaration, _ = ClashContributionDeclaration.objects.update_or_create(
        encounter=participant.encounter,
        round_number=round_number,
        participant=participant,
        clash=clash,
        defaults={
            "action_slot": action_slot,
            "technique": technique,
            "strain_commitment": strain_commitment,
        },
    )
    return declaration
