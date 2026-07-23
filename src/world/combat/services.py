"""Service functions for combat encounter lifecycle."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterator
import contextlib
from dataclasses import dataclass
from decimal import Decimal
import logging
import math
import random
from typing import TYPE_CHECKING, TypeVar

from django.db import transaction
from django.db.models import F, Prefetch, Q, Sum
from django.utils import timezone

if TYPE_CHECKING:
    from datetime import datetime

    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from actions.models.consequence_pools import ConsequencePool
    from flows.events.payloads import DamageSource
    from typeclasses.characters import Character
    from world.areas.positioning.models import Position, RampartElementProfile
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.checks.types import CheckResult, ModifierBreakdown, PendingResolution
    from world.combat.models import ClashConfig, CombatMark, StrainConfig
    from world.combat.types import WeaponContribution
    from world.conditions.models import ConditionInstance, ConditionTemplate, DamageType
    from world.conditions.types import (
        AppliedConditionResult,
        DamageInteractionResult,
        RemovedConditionResult,
    )
    from world.covenants.models import CovenantRole
    from world.items.models import ItemInstance
    from world.magic.models import FuryTier, Technique
    from world.magic.models.anima import CharacterAnima
    from world.magic.models.techniques import AbstractDamageProfile
    from world.magic.types import TechniqueUseResult
    from world.magic.types.power_ledger import PowerLedger
    from world.mechanics.models import ObjectProperty
    from world.scenes.models import Interaction, Persona
    from world.stories.models import Story
    from world.vitals.models import CharacterVitals

    PerformCheckFn = Callable[..., CheckResult]

from actions.errors import ActionDispatchError
from flows.constants import EventName
from flows.emit import emit_event
from flows.events.payloads import (
    AttackPreResolvePayload,
    CharacterIncapacitatedPayload,
    CharacterKilledPayload,
    CombatRoundStartingPayload,
    DamageAppliedPayload,
    DamagePreApplyPayload,
    EncounterCompletedPayload,
)
from world.checks.constants import ModifierSourceKind
from world.checks.services import collect_check_modifiers, perform_check
from world.checks.types import ModifierContribution
from world.combat.constants import (
    ABSORPTION_CAP_PER_MOMENT,
    BAR_UNITS_PER_ROUND,
    BOSS_PARLEY_RESISTANCE_STEP,
    BREAK_NOVELTY_MULTIPLIER,
    CHARGE_CHECK_BONUS,
    CHARGE_DAMAGE_BONUS,
    CHARGE_MAX_HOPS,
    COMBO_MIN_SLOTS,
    DEFENSE_CRITICAL_MULTIPLIER,
    DEFENSE_FULL_MULTIPLIER,
    DEFENSE_NO_DAMAGE_THRESHOLD,
    DEFENSE_REDUCED_MULTIPLIER,
    DEFENSE_REDUCED_THRESHOLD,
    ELEVATION_ADVANTAGE_TARGET_NAME,
    ENEMY_LANE_CAP_PERCENT,
    ENTITY_TYPE_NPC,
    ENTITY_TYPE_PC,
    FLEE_PARTIAL_SUCCESS_LEVEL,
    INTERPOSE_BASE_FATIGUE_COST,
    JOUST_DECISIVE_MARGIN,
    LANCE_UNMOUNTED_PENALTY,
    NO_ROLE_SPEED_RANK,
    NPC_SPEED_RANK,
    PACING_FLOOR_ROUND_PADDING,
    PENETRATION_CHECK_TYPE_NAME,
    REACTIONS_PER_ROUND,
    SENT_FLYING_IMPACT_FRACTION,
    WINDUP_BLIND_DOWNGRADE,
    WINDUP_CALLED_OUT_DOWNGRADE,
    WINDUP_DOWNGRADE_STEP,
    WINDUP_FIZZLE_DOWNGRADES,
    WINDUP_GENERIC_TELEGRAPH,
    WINDUP_MIN_DAMAGE_SCALE,
    ActionCategory,
    BreakContributionKind,
    ClashFlavor,
    ClashResolution,
    CombatAllegiance,
    CombatManeuver,
    EncounterOutcome,
    EncounterType,
    EngagementLockStatus,
    OpponentStatus,
    OpponentTier,
    PaceMode,
    ParticipantStatus,
    StrikeDelivery,
    TargetingMode,
    TargetSelection,
    wind_penalty,
)
from world.combat.damage_source import classify_source
from world.combat.models import (
    BossPhase,
    BreakBarContribution,
    Clash,
    ClashContribution,
    ClashContributionDeclaration,
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    CombatRoundAction,
    CombatRoundActionTarget,
    ComboDefinition,
    ComboLearning,
    ComboSlot,
    CreatureTemplate,
    EncounterAftermathRule,
    EncounterRiskAcknowledgement,
    EngagementLock,
    FleeConfig,
    FleeTierModifier,
    PendingOpponentAttack,
    RoundChallengeDeclaration,
    ThreatPool,
    ThreatPoolEntry,
    ThreatRecord,
)
from world.combat.types import (
    ActionOutcome,
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
from world.conditions.constants import Allegiance
from world.fatigue.constants import EFFORT_CHECK_MODIFIER, EffortLevel
from world.fatigue.services import apply_fatigue, get_fatigue_penalty
from world.magic.constants import EffectKind
from world.mechanics.types import ChallengeResolutionResult
from world.scenes.constants import RoundStatus
from world.vitals.constants import (
    DEATH_HEALTH_THRESHOLD,
    KNOCKOUT_HEALTH_THRESHOLD,
    PERMANENT_WOUND_THRESHOLD,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Threat record helpers (#2020)
# ---------------------------------------------------------------------------


def get_or_create_threat_record(
    encounter: CombatEncounter,
    opponent: CombatOpponent,
    participant: CombatParticipant,
) -> ThreatRecord:
    """Get or create the ThreatRecord for an (opponent, participant) pairing (#2020).

    Args:
        encounter: The combat encounter.
        opponent: The NPC opponent.
        participant: The PC participant.

    Returns:
        The existing or newly-created ``ThreatRecord`` for this pairing.
    """
    record, _ = ThreatRecord.objects.get_or_create(
        encounter=encounter,
        opponent=opponent,
        participant=participant,
        defaults={"threat_value": 0},
    )
    return record


def accumulate_threat(
    encounter: CombatEncounter,
    opponent: CombatOpponent,
    participant: CombatParticipant,
    amount: int,
) -> None:
    """Increment the threat value for an (opponent, participant) pairing (#2020).

    Called from ``apply_damage_to_opponent`` (damage -> threat) and the taunt
    verb (#2015). ``amount`` is a positive integer; negative values are clamped
    to zero.

    Args:
        encounter: The combat encounter.
        opponent: The NPC opponent being threatened against.
        participant: The PC participant whose threat is accumulating.
        amount: The threat increment (clamped to >= 0).
    """
    record = get_or_create_threat_record(encounter, opponent, participant)
    record.threat_value = max(0, record.threat_value + amount)
    record.save(update_fields=["threat_value"])


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
    """Return True if the character has any active condition granting death_deferred.

    Delegates to the canonical shared helper in world.conditions.services so
    there is one query definition. Kept as a thin wrapper for call-site
    compatibility within this module.
    """
    from world.conditions.services import has_death_deferred  # noqa: PLC0415

    return has_death_deferred(character)


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

    Uses cached_singleton() — never get_or_create — because this is authored
    content; a fabricated row would have no check_type and silently break flee
    resolution. DoesNotExist propagates loudly. Mirrors
    get_penetration_check_type.
    """
    config = FleeConfig.objects.cached_singleton()
    if config is None:
        raise FleeConfig.DoesNotExist
    return config


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
        # Bond combat bonus (#2021): relationship co-combatant passive.
        from world.relationships.services import bond_combat_bonus  # noqa: PLC0415

        extra_contributions.extend(
            bond_combat_bonus(
                self.participant.character_sheet,
                self.participant.encounter,
            )
        )

        # Mounted-combat bonuses/penalties (#1843), composed at the same seam
        # as every other check contribution — provenance stays exhaustive.
        from world.items.constants import GearArchetype  # noqa: PLC0415

        character = self.participant.character_sheet.character
        weapon_archetype = _equipped_weapon_archetype(character)

        if self.action.maneuver == CombatManeuver.CHARGE:
            charge_bonus = CHARGE_CHECK_BONUS
            if weapon_archetype == GearArchetype.LANCE:
                charge_bonus *= 2
            extra_contributions.append(
                ModifierContribution(
                    source_kind=ModifierSourceKind.CHARACTER,
                    source_label="Charge",
                    value=charge_bonus,
                )
            )

        if weapon_archetype == GearArchetype.LANCE:
            from world.companions.mount_content import MOUNTED_CONDITION_NAME  # noqa: PLC0415
            from world.conditions.models import ConditionTemplate  # noqa: PLC0415
            from world.conditions.services import has_condition  # noqa: PLC0415

            mounted_template = ConditionTemplate.get_by_name(MOUNTED_CONDITION_NAME)
            if not has_condition(character, mounted_template):
                extra_contributions.append(
                    ModifierContribution(
                        source_kind=ModifierSourceKind.CHARACTER,
                        source_label="Unmounted Lance",
                        value=LANCE_UNMOUNTED_PENALTY,
                    )
                )

        # Wind-as-mechanic (#1555): a banded SCENE penalty on missile attacks
        # only. Guarded cheaply — skip the felt_exposure room lookup entirely
        # for melee/lance attacks, which stay untouched.
        if (
            weapon_archetype in (GearArchetype.RANGED, GearArchetype.THROWN)
            and self.participant.encounter.room is not None
        ):
            from world.locations.constants import StatKey  # noqa: PLC0415
            from world.locations.services import felt_exposure  # noqa: PLC0415

            wind_mod = wind_penalty(
                felt_exposure(self.participant.encounter.room, stat_key=StatKey.WIND)
            )
            if wind_mod:
                extra_contributions.append(
                    ModifierContribution(
                        source_kind=ModifierSourceKind.SCENE,
                        source_label="Wind",
                        value=wind_mod,
                    )
                )

        breakdown = collect_check_modifiers(
            self.participant.character_sheet,
            self.offense_check_type,
            scene=self.participant.encounter.scene,
            extra_contributions=extra_contributions,
        )
        extra_modifiers = breakdown.total

        # #2536 Task 5: thread the live round context so CHECK_BONUS situational
        # perks can fire on the technique's own offense check — the check-side
        # sibling of resolve_combat_technique's POWER_BONUS threading above.
        # holder/subject are both the checking character's own sheet (perform_check
        # only reads .resolution/.target off this); target mirrors the cast's
        # POWER_BONUS target resolution (_resolve_primary_target_sheet) so the same
        # target-keyed situations are reachable for CHECK_BONUS perks too.
        from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
        from world.covenants.perks.context import SituationContext  # noqa: PLC0415

        situation_ctx = SituationContext(
            holder=self.participant.character_sheet,
            subject=self.participant.character_sheet,
            target=_resolve_primary_target_sheet(self.action),
            resolution=CombatRoundContext(self.participant),
        )
        return check_fn(
            character,
            self.offense_check_type,
            extra_modifiers=extra_modifiers,
            fatigue_penalty=penalty,
            situation_ctx=situation_ctx,
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

    def _filter_by_target_prerequisites(
        self, technique: Technique, opponents: list[CombatOpponent]
    ) -> list[CombatOpponent]:
        """Silently drop opponents that fail technique.target_prerequisites.

        AREA/FILTERED_GROUP only — these are enumerated independently of
        _build_affected_targets/_check_combat_target_prerequisites (which now
        skips AREA/FILTERED_GROUP entirely, deferring to this method, #1793
        second-pass fix), so a target_prerequisites-gated technique would
        otherwise land on every opponent regardless of eligibility. Mirrors
        resolve_targets' silent AREA/FILTERED_GROUP filter
        (world/magic/services/targeting.py) rather than raising — an AoE cast
        is expected to skip ineligible targets, not block the whole cast
        (ADR-0045).
        """
        from world.mechanics.services import prerequisites_met  # noqa: PLC0415

        prereqs = technique.cached_target_prerequisites
        if not prereqs:
            return opponents
        caster_od = self.participant.character_sheet.character
        eligible = []
        for opp in opponents:
            target_od = opp.objectdb
            if target_od is None:
                continue  # can't evaluate a Property-based prerequisite without an ObjectDB
            if prerequisites_met(prereqs, caster_od, target_od):
                eligible.append(opp)
        return eligible

    def _resolved_opponent_targets(self) -> list[CombatOpponent]:
        """Return the ordered list of CombatOpponents to act on for this action.

        - AREA: returns ALL non-DEFEATED opponents in the encounter, enumerated
          directly from the encounter (one query, no join table required).
          The client does NOT need to enumerate them at declaration time —
          the encounter is the source of truth for "who is targetable".
        - FILTERED_GROUP: returns only the opponents stored in the
          ``CombatRoundActionTarget`` join table (the explicitly-stored subset).
          Falls back to the single ``focused_opponent_target`` when no join rows
          exist (e.g. direct callers that bypass dispatch).
        - SINGLE / SELF (default): returns a one-element list containing only
          ``focused_opponent_target``, preserving pre-AoE behavior exactly.

        DEFEATED opponents are NOT filtered here for FILTERED_GROUP / SINGLE —
        callers skip them individually so that per-target status checks are fresh
        after each preceding target's damage write.  AREA is the exception: it
        pre-filters to exclude DEFEATED so clients never need to enumerate the
        full list.

        AREA and FILTERED_GROUP additionally run technique.target_prerequisites
        through ``_filter_by_target_prerequisites`` (silent filter, #1793) — the
        SINGLE/SELF branch does not, since that case is hard-gated pre-flight by
        ``_check_combat_target_prerequisites`` in ``resolve_combat_technique``
        before this method is ever reached for an AoE-independent enumeration.
        """
        from actions.constants import ActionTargetType  # noqa: PLC0415

        technique = self.action.focused_action
        if technique is None:
            primary = self.action.focused_opponent_target
            return [primary] if primary is not None else []

        target_type = technique.target_type
        if target_type == ActionTargetType.AREA:
            # Enumerate ALL active (non-DEFEATED) opponents in the encounter.
            # One query; no join-table rows required.
            opponents = list(
                CombatOpponent.objects.filter(
                    encounter=self.participant.encounter,
                )
                .exclude(status=OpponentStatus.DEFEATED)
                .order_by("pk")
            )
            return self._filter_by_target_prerequisites(technique, opponents)

        if target_type == ActionTargetType.FILTERED_GROUP:
            join_opponents = list(
                CombatRoundActionTarget.objects.filter(
                    action=self.action,
                    opponent__isnull=False,
                )
                .select_related("opponent")
                .order_by("pk")
            )
            if join_opponents:
                opponents = [row.opponent for row in join_opponents]
            else:
                # Fallback: a direct caller that didn't write join rows
                primary = self.action.focused_opponent_target
                opponents = [primary] if primary is not None else []
            return self._filter_by_target_prerequisites(technique, opponents)

        # SINGLE / SELF: single target only
        primary = self.action.focused_opponent_target
        return [primary] if primary is not None else []

    def _apply_profiles_to_target(  # noqa: PLR0913
        self,
        target: CombatOpponent,
        profiles: list[AbstractDamageProfile],
        weapon: WeaponContribution | None,
        *,
        sl: int,
        multiplier: Decimal,
        eff_intensity: int,
    ) -> tuple[list[OpponentDamageResult], bool]:
        """Apply each damage profile to a single target, returning results and weapon-hit flag.

        Skips profiles that deal zero damage and aborts early if the target is
        defeated mid-loop (can happen when a preceding profile triggers a kill).
        """
        results: list[OpponentDamageResult] = []
        weapon_landed = False
        for profile in profiles:
            scaled, profile_damage_type = self._profile_damage(
                profile, weapon, target, sl=sl, multiplier=multiplier, eff_intensity=eff_intensity
            )
            if scaled <= 0:
                continue
            target.refresh_from_db()
            if target.status == OpponentStatus.DEFEATED:
                break
            results.append(
                apply_damage_to_opponent(
                    target,
                    scaled,
                    damage_type=profile_damage_type,
                    source_sheet=self.participant.character_sheet,
                    # #2643: the profile IS in hand here — the cleanest seam to thread
                    # execute from (mirrors how damage_intensity_multiplier reaches
                    # compute_damage_budget above, in _profile_damage).
                    execute_missing_health_multiplier=profile.execute_missing_health_multiplier,
                )
            )
            weapon_landed = weapon_landed or (profile.uses_equipped_weapon and weapon is not None)
        return results, weapon_landed

    def _apply_damage(
        self, check_result: CheckResult, *, eff_intensity: int
    ) -> list[OpponentDamageResult]:
        """Iterate technique.damage_profiles against all resolved opponent targets.

        For AREA / FILTERED_GROUP techniques every opponent in the join table is
        attacked separately with the same profile contest (per-target soak /
        resistance applies independently).  SINGLE / SELF techniques are unchanged
        — only ``focused_opponent_target`` is used.

        Combines the technique's own profiles with its signed
        SignatureMotifBonus's profiles, if any (#1728) — both are
        ``AbstractDamageProfile`` subclasses, so weapon-augment, SL-multiplier,
        property-bonus, and multi-target all apply uniformly to both.

        Per opponent:
        - skip if DEFEATED (checked fresh after each preceding write)
        - for each damage profile: compute budget, apply SL multiplier, call
          apply_damage_to_opponent (subtracts soak + resistance)

        Returns one OpponentDamageResult per successfully applied profile×target
        combination.
        """
        from world.conditions.services import get_damage_multiplier  # noqa: PLC0415
        from world.magic.services.signature_effects import (  # noqa: PLC0415
            signature_damage_profiles,
        )

        targets = self._resolved_opponent_targets()
        if not targets:
            return []

        technique = self.action.focused_action
        attacker = self.participant.character_sheet.character
        profiles = list(technique.damage_profiles.select_related("damage_type").all())
        profiles += signature_damage_profiles(attacker, technique)
        if not profiles:
            return []

        sl = check_result.success_level
        multiplier = get_damage_multiplier(sl)
        if multiplier <= 0:
            return []

        weapon = effective_weapon_profile(attacker)
        any_weapon_landed = False

        results: list[OpponentDamageResult] = []
        for target in targets:
            target.refresh_from_db()
            if target.status == OpponentStatus.DEFEATED:
                continue
            target_results, weapon_landed = self._apply_profiles_to_target(
                target, profiles, weapon, sl=sl, multiplier=multiplier, eff_intensity=eff_intensity
            )
            results.extend(target_results)
            any_weapon_landed = any_weapon_landed or weapon_landed

        if any_weapon_landed:
            _wear_equipped_weapon(attacker)
        return results

    def _profile_damage(  # noqa: PLR0913
        self,
        profile: AbstractDamageProfile,
        weapon: WeaponContribution | None,
        target: CombatOpponent,
        *,
        sl: int,
        multiplier: Decimal,
        eff_intensity: int,
    ) -> tuple[int, DamageType | None]:
        """Scaled damage + effective damage_type for one profile (0 if it skips).

        Returns ``(0, None)`` when the profile's minimum_success_level exceeds
        ``sl``; otherwise folds the equipped weapon's contribution, a CHARGE
        maneuver's flat CHARGE_DAMAGE_BONUS (#1843, doubled for a LANCE), and
        the target's Property-driven damage bonus (#1793) into the formula
        budget, then applies the success-level multiplier. Budget is floored
        at 0 after the (possibly negative) property bonus is applied.
        """
        from world.mechanics.services import property_damage_bonus  # noqa: PLC0415

        if sl < profile.minimum_success_level:
            return 0, None
        budget = profile.compute_damage_budget(
            effective_power=eff_intensity,
            success_level=sl,
        )
        budget, profile_damage_type = _weapon_augmented_budget(
            profile, budget, weapon, self.participant.character_sheet
        )
        if self.action.maneuver == CombatManeuver.CHARGE:
            from world.items.constants import GearArchetype  # noqa: PLC0415

            charge_damage_bonus = CHARGE_DAMAGE_BONUS
            character = self.participant.character_sheet.character
            if _equipped_weapon_archetype(character) == GearArchetype.LANCE:
                charge_damage_bonus *= 2
            budget += charge_damage_bonus
        budget = max(0, budget + property_damage_bonus(target.objectdb, profile_damage_type))
        return int(budget * multiplier), profile_damage_type

    def _apply_conditions(
        self,
        check_result: CheckResult,
        *,
        eff_intensity: int,
    ) -> tuple[list[AppliedConditionResult], list[RemovedConditionResult]]:
        """Apply technique-authored conditions to appropriate targets.

        Resolves each ConditionTargetKind (SELF/ALLY/ENEMY) to a concrete list
        of ObjectDBs, builds the ``targets_by_kind`` mapping, and delegates to
        the shared ``apply_technique_conditions`` service — then runs the
        ``remove_technique_conditions`` dispel sibling over the same resolved
        targets (#1585).

        For AREA / FILTERED_GROUP techniques the ENEMY slot is expanded to ALL
        active (non-DEFEATED) opponents in ``_resolved_opponent_targets()`` rather
        than just the single ``focused_opponent_target``.

        ``eff_intensity`` is the combined effective intensity (injected power + pull bumps)
        computed by ``__call__`` and forwarded here.

        Returns:
            ``(applied, removed)`` — the apply results and the dispel results, both
            over the same resolved ``targets_by_kind``.
        """
        from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415
        from world.magic.services.condition_application import (  # noqa: PLC0415
            apply_technique_conditions,
            remove_technique_conditions,
        )

        technique = self.action.focused_action
        caster_od = self.participant.character_sheet.character

        targets_by_kind: dict[str, list] = {}

        # SELF and ALLY resolve to a single target (unchanged)
        for kind in (ConditionTargetKind.SELF, ConditionTargetKind.ALLY):
            target = _resolve_condition_target(kind, self.action, caster_od)
            if target is not None:
                targets_by_kind[kind] = [target]

        # ENEMY: expand to all resolved opponents for AoE; single for SINGLE/SELF
        enemy_objectdbs = _resolve_enemy_condition_targets(
            self._resolved_opponent_targets(), self.action, caster_od
        )
        if enemy_objectdbs:
            targets_by_kind[ConditionTargetKind.ENEMY] = enemy_objectdbs

        position_params: dict[str, int] = {}
        if self.action.cast_destination_id:
            position_params["destination_position_id"] = self.action.cast_destination_id
        if self.action.cast_position_a_id and self.action.cast_position_b_id:
            position_params["position_a_id"] = self.action.cast_position_a_id
            position_params["position_b_id"] = self.action.cast_position_b_id

        applied = apply_technique_conditions(
            technique=technique,
            success_level=check_result.success_level,
            eff_intensity=eff_intensity,
            targets_by_kind=targets_by_kind,
            source_character=caster_od,
            position_params=position_params or None,
        )
        # Signature-motif bonus (#1582): apply the signed technique's bonus conditions
        # through the SAME shared seam, over the same resolved targets. No-op when the
        # technique is not signed or the bonus carries no condition rows.
        from world.magic.services.signature_effects import (  # noqa: PLC0415
            apply_signature_bonus_conditions,
        )

        applied.extend(
            apply_signature_bonus_conditions(
                character=caster_od,
                technique=technique,
                success_level=check_result.success_level,
                eff_intensity=eff_intensity,
                targets_by_kind=targets_by_kind,
                source_character=caster_od,
            )
        )
        # Dispel/cleanse sibling (#1585): strip technique-authored conditions from
        # the same resolved targets. No-op when the technique has no
        # removed_conditions rows.
        removed = remove_technique_conditions(
            technique=technique,
            success_level=check_result.success_level,
            targets_by_kind=targets_by_kind,
            source_character=caster_od,
        )
        return applied, removed

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
            scene=self.participant.encounter.scene,
        )
        # #2536 Task 5 review fix: thread the same live round context the
        # offense check gets (_roll_check) — same class, same self.participant,
        # same target resolution. A future CHECK_BONUS perk scoped to the
        # penetration CheckType must not silently never fire just because this
        # sibling roll skipped the seam every other combat check now honors.
        from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
        from world.covenants.perks.context import SituationContext  # noqa: PLC0415

        situation_ctx = SituationContext(
            holder=self.participant.character_sheet,
            subject=self.participant.character_sheet,
            target=_resolve_primary_target_sheet(self.action),
            resolution=CombatRoundContext(self.participant),
        )
        pen_result = perform_check(
            caster,
            pen_check_type,
            target_difficulty=ward,
            extra_modifiers=pen_breakdown.total,
            situation_ctx=situation_ctx,
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

    def __call__(
        self,
        *,
        power: int,  # noqa: ARG002
        ledger: PowerLedger,
        extra_modifiers: int = 0,  # noqa: ARG002
    ) -> CombatTechniqueResolution:
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
        applied_conditions, removed_conditions = self._apply_conditions(
            check_result, eff_intensity=eff_intensity
        )
        return CombatTechniqueResolution(
            check_result=check_result,
            damage_results=damage_results,
            applied_conditions=applied_conditions,
            pull_flat_bonus=self.pull_flat_bonus,
            scaled_damage=sum(r.damage_dealt for r in damage_results),
            power_ledger=combat_ledger,
            removed_conditions=removed_conditions,
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


def _resolve_enemy_condition_targets(
    all_opponents: list[CombatOpponent],
    action: CombatRoundAction,
    caster_od: ObjectDB,
) -> list[ObjectDB]:
    """Resolve the ENEMY condition target list for ``_apply_conditions``.

    AREA / FILTERED_GROUP techniques expand ENEMY to ALL active (non-DEFEATED)
    opponents in ``_resolved_opponent_targets()``; when there are no join-table
    opponents, fall back to the single focused target.
    """
    from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415

    if all_opponents:
        enemy_objectdbs: list[ObjectDB] = []
        for opp in all_opponents:
            opp.refresh_from_db()
            if opp.status != OpponentStatus.DEFEATED and opp.objectdb is not None:
                enemy_objectdbs.append(opp.objectdb)
        return enemy_objectdbs
    # No join-table opponents — fall back to the single focused target
    target = _resolve_condition_target(ConditionTargetKind.ENEMY, action, caster_od)
    return [target] if target is not None else []


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


def _resolve_primary_target_sheet(action: CombatRoundAction) -> CharacterSheet | None:
    """Resolve the cast's primary target's ``CharacterSheet`` for situational perks (#2536).

    Mirrors ``_build_affected_targets``'s ordering (opponent target takes
    precedence over ally target when a technique somehow declares both — the
    dispatcher never actually does this, but the ordering is kept consistent).
    Only a PC/sheet-backed target can populate a ``CharacterSheet``:

    - ``focused_ally_target`` → ``CombatParticipant.character_sheet`` (always
      a real ``CharacterSheet`` — every ``CombatParticipant`` is a PC).
    - ``focused_opponent_target`` → a ``CombatOpponent`` is NPC-only and has
      no ``CharacterSheet`` FK of its own, UNLESS it is a "story NPC" linked
      to a persistent ``scenes.Persona`` (``CombatOpponent.persona``, see
      ``world/combat/escalation.py``'s ``opponent.persona.character_sheet``
      for the same resolution pattern) — that gives a real ``CharacterSheet``
      target-keyed situations can read. A bare (non-persona) NPC opponent
      correctly resolves to ``None``: target-keyed situations (
      ``TARGET_DISTRACTED``/``TARGET_SWAYED_BY_ALLY``/
      ``TARGET_FOCUSED_ELSEWHERE``/``TARGET_FAVORABLY_DISPOSED``) simply
      never hold against it, same as any other targetless cast.

    For a multi-target/AoE cast only this single primary target is resolved
    — per-target perk evaluation for AoE is a legitimate slice-2+
    refinement (see ``vow_situational_power_term``'s docstring).
    """
    if action.focused_opponent_target_id:
        opponent = action.focused_opponent_target
        if opponent.persona_id is not None:
            return opponent.persona.character_sheet
        return None
    if action.focused_ally_target_id:
        return action.focused_ally_target.character_sheet
    return None


def _check_combat_target_prerequisites(
    technique: Technique, caster_od: ObjectDB, targets: list[ObjectDB]
) -> None:
    """Enforce technique.target_prerequisites against combat's explicit target list.

    SINGLE is the only target_type that hard-blocks here: its target list
    (from _build_affected_targets) is the real, complete target set for the
    cast, so a failure hard-blocks the cast — mirroring the non-combat
    SINGLE hard-block in validate_cast_target.

    For target_type=SELF, the caster IS the target — but the real cast dispatcher
    (``_target_spec_for_technique_action`` in ``actions/player_interface.py``) never
    supplies an explicit opponent/ally target for a SELF technique, so
    ``_build_affected_targets`` returns [] (see
    ``test_affected_emitted_for_self_targeted_buff``). Check the caster directly in
    that case rather than relying on targets being populated — mirrors Task 5's
    non-combat SELF fix in ``world/magic/services/targeting.py``.

    AREA/FILTERED_GROUP get NO pre-flight check at all: ``targets`` here is built
    from ``action.focused_opponent_target``, a single FK that for an AoE dispatch
    holds only the arbitrary "first" opponent from a client-supplied
    ``focused_opponent_target_ids`` list (see
    ``RoundContext._resolve_focused_targets``) — not a real single target, and not
    the full AoE set. Hard-blocking the whole cast because THAT one arbitrary
    opponent fails a prerequisite would wrongly kill a cast where other opponents
    in the same AoE set legitimately pass. Defer entirely to
    ``_filter_by_target_prerequisites``'s silent per-opponent filter downstream
    (``_resolved_opponent_targets``, #1793 second-pass fix).
    """
    from actions.constants import ActionTargetType  # noqa: PLC0415
    from world.magic.services.targeting import InvalidCastTarget  # noqa: PLC0415
    from world.mechanics.services import prerequisites_met  # noqa: PLC0415

    prereqs = technique.cached_target_prerequisites
    if not prereqs:
        return

    if technique.target_type in (ActionTargetType.AREA, ActionTargetType.FILTERED_GROUP):
        return

    msg = "Target does not meet this technique's targeting requirement."

    if technique.target_type == ActionTargetType.SELF:
        if not prerequisites_met(prereqs, caster_od, caster_od):
            raise InvalidCastTarget(msg)
        return

    for target_od in targets:
        if not prerequisites_met(prereqs, caster_od, target_od):
            raise InvalidCastTarget(msg)


def combatants_hostile_to(
    actor: CombatParticipant | CombatOpponent,
) -> dict[str, list]:
    """Return the combatants *actor* may attack, grouped by kind.

    Single source of truth for friend/foe resolution (Tasks 7 and 13 use this):

    - A PC participant is hostile to ENEMY opponents (not to ALLY summons).
    - An ALLY opponent (summon/charmed) is hostile to ENEMY opponents only.
    - An ENEMY opponent is hostile to PCs *and* any ALLY summons.
    """
    enc = actor.encounter
    active_pcs = list(
        CombatParticipant.objects.filter(encounter=enc, status=ParticipantStatus.ACTIVE)
    )
    enemies = list(
        CombatOpponent.objects.filter(
            encounter=enc, status=OpponentStatus.ACTIVE, allegiance=CombatAllegiance.ENEMY
        )
    )
    allies = list(
        CombatOpponent.objects.filter(
            encounter=enc, status=OpponentStatus.ACTIVE, allegiance=CombatAllegiance.ALLY
        )
    )
    if isinstance(actor, CombatParticipant) or actor.allegiance == CombatAllegiance.ALLY:
        # PC side: hostile to ENEMY opponents only.
        return {"participants": [], "opponents": enemies}
    # ENEMY opponent: hostile to PCs and any ALLY summons.
    return {"participants": active_pcs, "opponents": allies}


def _build_combat_result(
    technique_use_result: TechniqueUseResult,
    resolver: CombatTechniqueResolver,  # noqa: ARG001 - kept for future extensibility
    fury_committed: FuryTier | None = None,
) -> CombatTechniqueResult:
    """Translate use_technique's outcome into the adapter's return shape."""
    if not technique_use_result.confirmed:
        return CombatTechniqueResult(
            damage_results=[],
            applied_conditions=[],
            technique_use_result=technique_use_result,
            fury_committed=fury_committed,
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
        fury_committed=fury_committed,
        removed_conditions=list(resolution.removed_conditions),
    )


def _vulnerability_intensity_bonus(action: CombatRoundAction) -> int:
    """Return the break-bar vulnerability intensity bonus if the action's
    target opponent is currently vulnerable, else 0.
    """
    target = action.focused_opponent_target
    if target is None or target.vulnerability_rounds_remaining <= 0:
        return 0
    return target.vulnerability_intensity_bonus


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
    from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
    from world.magic.services import use_technique  # noqa: PLC0415
    from world.magic.services.fury import run_fury_for_action  # noqa: PLC0415

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
    _check_combat_target_prerequisites(
        action.focused_action, participant.character_sheet.character, targets
    )

    fury_res = run_fury_for_action(
        character=participant.character_sheet.character,
        fury_commitment=action.fury_commitment,
        fury_anchor=action.fury_anchor,
        source_technique=action.focused_action,
    )

    # Signature-motif bonus (#1582): a flat intensity delta on the signed technique's
    # thread folds into power derivation, exactly as in the standalone cast path
    # (no-op / 0 when unsigned).
    from world.magic.services.signature_effects import signature_intensity_delta  # noqa: PLC0415

    sig_intensity_delta = signature_intensity_delta(
        participant.character_sheet.character, action.focused_action
    )

    technique_use_result = use_technique(
        character=participant.character_sheet.character,
        technique=action.focused_action,
        resolve_fn=resolver,
        confirm_soulfray_risk=action.confirm_soulfray_risk,
        targets=targets,
        lethal=encounter.is_lethal,
        control_penalty=fury_res.control_penalty if fury_res else 0,
        power_intensity_bonus=(
            (fury_res.intensity_bonus if fury_res else 0)
            + sig_intensity_delta
            + _vulnerability_intensity_bonus(action)
        ),
        # #2536 Task 4: thread the live round context so situational-perk
        # POWER_BONUS providers can read combat-positioning situations
        # (AT_RANGE/IN_MELEE/SURROUNDED/...). Cheap to build — CombatRoundContext
        # just wraps the already-resolved participant (its encounter rides the
        # SharedMemoryModel identity map), no extra query.
        situation_ctx=CombatRoundContext(participant),
        # #2536 Task 4 review fix: thread the cast's primary target's
        # CharacterSheet so target-keyed situational-perk POWER_BONUS
        # providers (TARGET_DISTRACTED/TARGET_SWAYED_BY_ALLY/
        # TARGET_FOCUSED_ELSEWHERE/TARGET_FAVORABLY_DISPOSED) can fire.
        target_sheet=_resolve_primary_target_sheet(action),
    )

    return _build_combat_result(
        technique_use_result, resolver, fury_committed=fury_res.realized_tier if fury_res else None
    )


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


def _create_participant(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
    *,
    covenant_role: CovenantRole | None = None,
    status: str = ParticipantStatus.ACTIVE,
) -> CombatParticipant:
    """Create a CombatParticipant + its engagement, and record the fighter as a
    scene participant (combat participation implies SceneParticipation, #1236)."""
    if covenant_role is None:
        from world.covenants.services import precedence_role_for_combat  # noqa: PLC0415

        covenant_role = precedence_role_for_combat(character_sheet)
    participant = CombatParticipant.objects.create(
        encounter=encounter,
        character_sheet=character_sheet,
        covenant_role=covenant_role,
        status=status,
    )
    _ensure_combat_engagement(participant)

    from world.combat.escalation import check_hated_foe_surges_for_new_participant  # noqa: PLC0415

    check_hated_foe_surges_for_new_participant(participant)

    if encounter.scene_id:
        from world.scenes.interaction_services import ensure_scene_participation  # noqa: PLC0415

        ensure_scene_participation(encounter.scene, character_sheet.character)
    return participant


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
    return _create_participant(encounter, character_sheet, covenant_role=covenant_role)


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
    ack, created = EncounterRiskAcknowledgement.objects.get_or_create(
        encounter=encounter,
        character_sheet=character_sheet,
        defaults={"acknowledged_risk_level": encounter.risk_level},
    )
    # #2051: on first entry, warn a solo character entering a BOSS/HERO_KILLER
    # encounter — the stark darkness line, no gate (decision 2).
    if created:
        _maybe_warn_solo_boss_entry(encounter, character_sheet)
    return ack


def _maybe_warn_solo_boss_entry(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
) -> None:
    """Send the solo darkness warning if entering a BOSS/HERO_KILLER encounter alone (#2051)."""
    from world.combat.constants import OpponentTier  # noqa: PLC0415
    from world.missions.constants import SOLO_DARKNESS_WARNING  # noqa: PLC0415

    has_boss = CombatOpponent.objects.filter(
        encounter=encounter,
        tier__in=(OpponentTier.BOSS, OpponentTier.HERO_KILLER),
        status=OpponentStatus.ACTIVE,
    ).exists()
    if not has_boss:
        return
    # Check if the character is the only active participant (solo).
    active_count = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).count()
    if active_count > 1:
        return
    character_sheet.character.msg(SOLO_DARKNESS_WARNING)


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
    allowed = {RoundStatus.DECLARING, RoundStatus.BETWEEN_ROUNDS}
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

    participant = _create_participant(
        encounter, character_sheet, covenant_role=covenant_role, status=ParticipantStatus.ACTIVE
    )
    acknowledge_encounter_risk(encounter, character_sheet)
    return participant


@transaction.atomic
def leave_encounter(participant: CombatParticipant) -> None:
    """Allow a participant to voluntarily leave an Open Encounter between rounds.

    Unlike flee (a check-gated exit), this is unconditional. If the departing
    participant is the last active participant, the encounter completes as ABANDONED.

    Raises ValueError when:
    - the encounter is not in BETWEEN_ROUNDS status,
    - the encounter type is not OPEN_ENCOUNTER, or
    - the participant is not ACTIVE.
    """
    enc = CombatEncounter.objects.select_for_update().get(pk=participant.encounter_id)
    if enc.status != RoundStatus.BETWEEN_ROUNDS:
        msg = (
            f"Cannot leave: encounter status is "
            f"'{enc.get_status_display()}', expected 'Between Rounds'."
        )
        raise ValueError(msg)
    if enc.encounter_type != EncounterType.OPEN_ENCOUNTER:
        msg = (
            f"Cannot leave: encounter type is "
            f"'{enc.get_encounter_type_display()}', expected 'Open Encounter'."
        )
        raise ValueError(msg)
    # Re-read participant under the same transaction lock to avoid stale status reads.
    participant = CombatParticipant.objects.select_for_update().get(pk=participant.pk)
    if participant.status != ParticipantStatus.ACTIVE:
        msg = f"Cannot leave: participant status is '{participant.status}'."
        raise ValueError(msg)

    remove_participant(participant)

    any_active = CombatParticipant.objects.filter(
        encounter=enc,
        status=ParticipantStatus.ACTIVE,
    ).exists()
    if not any_active:
        complete_encounter(enc, outcome=EncounterOutcome.ABANDONED)


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
    if encounter.status != RoundStatus.DECLARING:
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


def toggle_action_ready(action: CombatRoundAction) -> CombatRoundAction:
    """Flip the ready flag on a round action and persist it.

    Extracted from the inline toggle that lived in the web ``ready`` endpoint so
    both the telnet/web shared ``ReadyAction`` and any caller use one code path.
    """
    action.is_ready = not action.is_ready
    action.save(update_fields=["is_ready"])
    return action


def maybe_resolve_on_ready(encounter: CombatEncounter) -> RoundResolutionResult | None:
    """Resolve the round early when every ACTIVE participant is ready (#2120).

    Only applies in ``PaceMode.READY`` — ``TIMED`` encounters keep resolving via
    the game-clock sweep (``check_and_resolve_timed_encounters``); ``MANUAL``
    encounters resolve only on an explicit GM/force-resolve call. Compares the
    ACTIVE participant count against this round's ``is_ready=True``
    ``CombatRoundAction`` count; when they're equal (and non-zero — an
    encounter with no active participants never fires), ``resolve_round`` is
    called. Returns the resolution result, or ``None`` when the round didn't
    resolve.
    """
    if encounter.pace_mode != PaceMode.READY:
        return None
    if encounter.status != RoundStatus.DECLARING:
        return None

    active_count = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).count()
    if active_count == 0:
        return None

    ready_count = CombatRoundAction.objects.filter(
        participant__encounter=encounter,
        round_number=encounter.round_number,
        is_ready=True,
    ).count()
    if ready_count != active_count:
        return None

    return resolve_round(encounter)


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
    if encounter.status != RoundStatus.DECLARING:
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


def declare_use_item(
    participant: CombatParticipant,
    item_instance: ItemInstance,
    *,
    target: CombatParticipant | CombatOpponent | None = None,
) -> CombatRoundAction:
    """Declare using a held on-use item as this round's action (#2023, #2120).

    Unlike FLEE/COVER (passives-only), USE_ITEM is a primary maneuver -- it is
    mutually exclusive with a declared focused technique, consuming the round's
    action slot. ``target`` may be a ``CombatParticipant`` (ally/self target) or
    a ``CombatOpponent`` (enemy target); it is resolved into
    ``focused_ally_target``/``focused_opponent_target`` respectively, reusing
    the existing FK slots rather than adding a new field. Resolution
    (``_resolve_use_item``) dispatches the existing ``UseItemAction`` machinery.
    """
    from flows.object_states.item_state import ItemState  # noqa: PLC0415
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot use item: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot use item: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot use item: character is dead."
        raise ValueError(msg)

    character = participant.character_sheet.character
    # Same wrap-without-context call HoldsItemPrerequisite uses for possession checks.
    item_state = ItemState(item_instance, context=None)  # ty: ignore[invalid-argument-type]
    if not item_state.is_in_possession(character):
        msg = "Cannot use item: you aren't holding it."
        raise ValueError(msg)

    ally_target: CombatParticipant | None = None
    opponent_target: CombatOpponent | None = None
    if isinstance(target, CombatParticipant):
        if target.encounter_id != encounter.pk or target.status != ParticipantStatus.ACTIVE:
            msg = "Use-item target must be an active participant in this encounter."
            raise ValueError(msg)
        ally_target = target
    elif isinstance(target, CombatOpponent):
        if target.encounter_id != encounter.pk or target.status != OpponentStatus.ACTIVE:
            msg = "Use-item target must be an active opponent in this encounter."
            raise ValueError(msg)
        opponent_target = target
    elif target is not None:
        msg = "Invalid use-item target type."
        raise ValueError(msg)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.MEDIUM,
            "focused_opponent_target": opponent_target,
            "focused_ally_target": ally_target,
            "maneuver": CombatManeuver.USE_ITEM,
            "item_instance": item_instance,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def resolve_cast_position_params(
    participant: CombatParticipant,
    technique: Technique,
    position_params: dict[str, int],
) -> dict[str, Position | None]:
    """Validate declared cast positions against the encounter's room + technique reach.

    ``position_params`` is the raw dispatch payload — either a single
    ``destination_position_id`` (single-position techniques such as Phase Jump /
    Force Grip / zone hazards) or a ``position_a_id``/``position_b_id`` pair
    (Barricade-style two-endpoint techniques). Both shapes are optional and
    mutually independent; an empty/absent ``position_params`` resolves to all-None.

    Raises ``ActionDispatchError`` (mirroring the existing ally-target /
    positional-reach error path used elsewhere in this module):

    - ``UNKNOWN_ACTION_REF`` — a supplied position id does not resolve to a
      ``Position`` in the encounter's own room, the a/b pair is only
      half-supplied, or the a/b pair is identical (a barrier needs two
      different endpoints).
    - ``TARGET_OUT_OF_REACH`` — the declared destination is beyond
      ``technique.reach`` from the caster's current position. Skipped when the
      caster is unplaced (no current_position) — lenient, same rationale as
      ``_validate_technique_reach``.
    """
    from world.areas.positioning.models import Position  # noqa: PLC0415
    from world.areas.positioning.services import position_reachable  # noqa: PLC0415

    room = participant.encounter.room
    resolved: dict[str, Position | None] = {
        "cast_destination": None,
        "cast_position_a": None,
        "cast_position_b": None,
    }

    def _get(pk: int) -> Position:
        pos = Position.objects.filter(pk=pk, room=room).first()
        if pos is None:
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)
        return pos

    dest_id = position_params.get("destination_position_id")
    if dest_id:
        dest = _get(dest_id)
        origin = participant.current_position
        if origin is not None and not position_reachable(
            origin, dest, technique.reach, reach_hops=technique.reach_hops
        ):
            raise ActionDispatchError(ActionDispatchError.TARGET_OUT_OF_REACH)
        resolved["cast_destination"] = dest

    a_id = position_params.get("position_a_id")
    b_id = position_params.get("position_b_id")
    if bool(a_id) != bool(b_id):
        raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)
    if a_id and b_id:
        if a_id == b_id:
            # A barrier needs two different endpoints — reject a degenerate pair
            # before it ever reaches the resolver.
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)
        resolved["cast_position_a"] = _get(a_id)
        resolved["cast_position_b"] = _get(b_id)

    return resolved


def _validate_redirect_declaration(
    encounter: CombatEncounter,
    redirect_opponent_target: CombatOpponent | None,
    redirect_object_target: ObjectDB | None,  # noqa: OBJECTDB_PARAM
) -> None:
    """Validate a redirect declaration's destination kwargs (#2210).

    Extracted from :func:`declare_interpose` to keep its complexity in check.
    Mutually exclusive; each populated kwarg is validated against the
    encounter it's being declared into. Both ``None`` ("away") needs no
    validation.
    """
    from world.mechanics.services import volatile_object_property  # noqa: PLC0415

    if redirect_opponent_target is not None and redirect_object_target is not None:
        msg = "Cannot interpose: choose at most one redirect destination."
        raise ValueError(msg)

    if redirect_opponent_target is not None and (
        redirect_opponent_target.encounter_id != encounter.pk
        or redirect_opponent_target.status != OpponentStatus.ACTIVE
    ):
        msg = "Redirect target must be an active opponent in this encounter."
        raise ValueError(msg)

    if redirect_object_target is not None:
        if redirect_object_target.db_location_id != encounter.room_id:
            msg = "Redirect target must be an object in the encounter room."
            raise ValueError(msg)
        if volatile_object_property(redirect_object_target) is None:
            msg = "Redirect target is not volatile."
            raise ValueError(msg)


def declare_interpose(
    participant: CombatParticipant,
    ally: CombatParticipant | None = None,
    technique: Technique | None = None,
    redirect_opponent_target: CombatOpponent | None = None,
    redirect_object_target: ObjectDB | None = None,  # noqa: OBJECTDB_PARAM
) -> CombatRoundAction:
    """Declare an interposing maneuver — passives-only, auto-ready.

    ``ally=None`` means the participant will guard any ally hit this round;
    when a specific ally is given they must be active and in the same encounter.

    ``technique=None`` (default) declares a plain interpose exactly as before
    #2207 — passives only, ``focused_action`` zeroed. Supplying a *technique*
    carries a protective reactive-trigger technique into the declaration: the
    participant must know it (``CharacterTechnique``) and it must classify to a
    protective flavor via ``protective_flavor`` (barrier/blink/redirect,
    `world/magic/services/targeting.py`).

    ``redirect_opponent_target``/``redirect_object_target`` (#2210) declare the
    destination for saved damage when the guardian's technique resolves as a
    REDIRECT flavor (Mirror Ward-style reflection) — declaration-time choice
    per ADR-0032. Mutually exclusive; both ``None`` means "away," the universal
    fallback destination. ``redirect_opponent_target`` must be an active
    (not-defeated) opponent in this same encounter. ``redirect_object_target``
    must be an ObjectDB located in the encounter's room AND "volatile" — it
    carries an ``ObjectProperty`` whose ``Property`` has a ``PropertyDetonation``
    row (see ``world.mechanics.services.volatile_object_property``). These
    kwargs are accepted regardless of the declared technique's flavor (harmless
    no-ops for non-REDIRECT declarations); resolution
    (``_try_technique_interpose``) only reads them on the REDIRECT branch.
    """
    from world.magic.models import CharacterTechnique  # noqa: PLC0415
    from world.magic.services.targeting import protective_flavor  # noqa: PLC0415
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot interpose: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot interpose: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot interpose: character is dead."
        raise ValueError(msg)

    if ally is not None:
        if ally.pk == participant.pk:
            msg = "Cannot interpose yourself."
            raise ValueError(msg)
        if ally.encounter_id != encounter.pk or ally.status != ParticipantStatus.ACTIVE:
            msg = "Interpose target must be an active participant in this encounter."
            raise ValueError(msg)

    if technique is not None:
        knows_technique = CharacterTechnique.objects.filter(
            character=participant.character_sheet,
            technique=technique,
        ).exists()
        if not knows_technique:
            msg = "Cannot interpose: character does not know that technique."
            raise ValueError(msg)
        flavor = protective_flavor(technique)
        if flavor is None:
            msg = "Cannot interpose: that technique cannot guard yet."
            raise ValueError(msg)

    _validate_redirect_declaration(encounter, redirect_opponent_target, redirect_object_target)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": technique,
            "focused_category": None,
            "effort_level": EffortLevel.VERY_LOW,
            "focused_opponent_target": None,
            "focused_ally_target": ally,
            "maneuver": CombatManeuver.INTERPOSE,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
            "redirect_opponent_target": redirect_opponent_target,
            "redirect_object_target": redirect_object_target,
        },
    )
    return action


def declare_mark(
    participant: CombatParticipant,
    opponent: CombatOpponent,
    *,
    technique: Technique | None = None,
) -> CombatMark:
    """Declare a mark — a directed, round-scoped combatant reference (#2664).

    A participant declares a target opponent for covenant-mates to focus.
    The mark persists for the round; old marks are ignored (query-scoped by
    ``round_number``). Generic combat primitive — vow content (perks, rungs)
    reads the mark via the ``TARGET_IS_MARKED_BY_ALLY`` situation evaluator.

    Validations mirror ``declare_interpose``: encounter must be in DECLARING
    status, participant must be ACTIVE, opponent must be ACTIVE and in the
    same encounter. Idempotent per round: re-declaring updates the same row.
    """
    from world.combat.constants import OpponentStatus, ParticipantStatus  # noqa: PLC0415
    from world.combat.models import CombatMark  # noqa: PLC0415
    from world.scenes.constants import RoundStatus  # noqa: PLC0415
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot mark: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot mark: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot mark: character is dead."
        raise ValueError(msg)

    if opponent.status != OpponentStatus.ACTIVE:
        msg = "Cannot mark a defeated or fled opponent."
        raise ValueError(msg)

    if opponent.encounter_id != encounter.pk:
        msg = "Cannot mark: opponent is not in this encounter."
        raise ValueError(msg)

    mark, _ = CombatMark.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "encounter": encounter,
            "opponent": opponent,
            "source_technique": technique,
        },
    )
    return mark


def declare_succor(
    participant: CombatParticipant,
    ally: CombatParticipant,
) -> CombatRoundAction:
    """Declare a sheltering maneuver for a specific ally — passives-only, auto-ready.

    Unlike Interpose (which can guard "any ally" against whichever attack lands),
    Succor always names a specific ally: environmental shelter is "I'm sheltering
    THIS person," not "I'll block whichever hazard lands on someone." Resolution
    happens later, at round-tick DoT application (#1744).
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot succor: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)
    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot succor: participant is no longer active in this encounter."
        raise ValueError(msg)
    if is_dead(participant.character_sheet):
        msg = "Cannot succor: character is dead."
        raise ValueError(msg)
    if ally.pk == participant.pk:
        msg = "Cannot succor yourself."
        raise ValueError(msg)
    if ally.encounter_id != encounter.pk or ally.status != ParticipantStatus.ACTIVE:
        msg = "Succor target must be an active participant in this encounter."
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
            "maneuver": CombatManeuver.SUCCOR,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
            "succor_resolution": None,
        },
    )
    return action


def declare_rally(
    participant: CombatParticipant,
    ally: CombatParticipant,
) -> CombatRoundAction:
    """Declare a rallying maneuver — inspire an ally, auto-ready (#2015).

    RALLY rolls a presence/Performance check at round-tick; on success it applies
    a short-lived ``Inspired`` condition to the ally (a damage-multiplier buff) and,
    on a great success, restores morale to ally-side summon opponents. This
    function only records the declaration.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot rally: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot rally: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot rally: character is dead."
        raise ValueError(msg)

    if ally.pk == participant.pk:
        msg = "Cannot rally yourself."
        raise ValueError(msg)
    if ally.encounter_id != encounter.pk or ally.status != ParticipantStatus.ACTIVE:
        msg = "Rally target must be an active participant in this encounter."
        raise ValueError(msg)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.LOW,
            "focused_opponent_target": None,
            "focused_ally_target": ally,
            "maneuver": CombatManeuver.RALLY,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def declare_demoralize(
    participant: CombatParticipant,
    opponent: CombatOpponent,
) -> CombatRoundAction:
    """Declare a demoralizing maneuver — break an opponent's nerve, auto-ready (#2015).

    DEMORALIZE rolls a presence/Persuasion(Intimidation) check at round-tick against
    the target's Composure; on success it depletes the target's morale. Mindless
    opponents resist (not immune). This function only records the declaration.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot demoralize: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot demoralize: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot demoralize: character is dead."
        raise ValueError(msg)

    if opponent.encounter_id != encounter.pk or opponent.status != OpponentStatus.ACTIVE:
        msg = "Demoralize target must be an active opponent in this encounter."
        raise ValueError(msg)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.MEDIUM,
            "focused_opponent_target": opponent,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.DEMORALIZE,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def declare_taunt(
    participant: CombatParticipant,
    opponent: CombatOpponent,
) -> CombatRoundAction:
    """Declare a taunting maneuver — draw an NPC's aggro, auto-ready (#2015).

    TAUNT rolls a wits/Persuasion(Intimidation) check at round-tick against the
    target's Composure; on success it accumulates threat on the existing
    ``ThreatRecord`` seam, biasing the NPC's target selection toward the taunter.
    This function only records the declaration.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot taunt: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot taunt: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot taunt: character is dead."
        raise ValueError(msg)

    if opponent.encounter_id != encounter.pk or opponent.status != OpponentStatus.ACTIVE:
        msg = "Taunt target must be an active opponent in this encounter."
        raise ValueError(msg)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.LOW,
            "focused_opponent_target": opponent,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.TAUNT,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def _parley_gate_met(
    participant: CombatParticipant,
    opponent: CombatOpponent,
) -> bool:
    """Return whether parley's precondition is met (#2015).

    Parley is gated: the opponent must be faltering or broken (morale below
    ``FALTER_MORALE_THRESHOLD``), OR the participant's persona must hold an
    ``NPCStanding`` with ``affection >= PARLEY_DISPOSITION_FLOOR`` toward the
    opponent's persona. A steady, unknown opponent cannot be parleyed with —
    but mindless targets are not rejected here (they roll with resistance at
    resolve time; a breakthrough grants a fleeting mind).
    """
    from world.combat.constants import PARLEY_DISPOSITION_FLOOR  # noqa: PLC0415
    from world.combat.morale import OpponentMoraleState, morale_state_for  # noqa: PLC0415

    if morale_state_for(opponent) != OpponentMoraleState.STEADY:
        return True

    # Steady opponent: check durable standing toward the opponent's persona.
    if opponent.persona_id is None:
        return False

    from world.npc_services.models import NPCStanding  # noqa: PLC0415
    from world.scenes.services import (  # noqa: PLC0415
        MissingPrimaryPersonaError,
        persona_for_character,
    )

    try:
        pc_persona = persona_for_character(participant.character_sheet.character)
    except MissingPrimaryPersonaError:
        # Half-set-up actor with no primary persona — no standing to check.
        return False

    return NPCStanding.objects.filter(
        persona=pc_persona,
        npc_persona_id=opponent.persona_id,
        affection__gte=PARLEY_DISPOSITION_FLOOR,
    ).exists()


def declare_parley(
    participant: CombatParticipant,
    opponent: CombatOpponent,
) -> CombatRoundAction:
    """Declare a parley maneuver — talk a foe down mid-fight, auto-ready (#2015).

    PARLEY is gated (see ``_parley_gate_met``): the opponent must be faltering/
    broken or the participant must hold sufficient standing. At round-tick it
    rolls a charm/Persuasion(Seduction) check against the target's Composure; on
    success it routes through ``apply_social_disposition_delta`` and, on a
    decisive success, calms the opponent (Calm condition → NEUTRAL allegiance).
    This function only records the declaration.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot parley: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot parley: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot parley: character is dead."
        raise ValueError(msg)

    if opponent.encounter_id != encounter.pk or opponent.status != OpponentStatus.ACTIVE:
        msg = "Parley target must be an active opponent in this encounter."
        raise ValueError(msg)

    if not _parley_gate_met(participant, opponent):
        msg = (
            "Cannot parley: the opponent's nerve is steady and you hold no "
            "standing with them. Break their resolve first, or build rapport."
        )
        raise ValueError(msg)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.MEDIUM,
            "focused_opponent_target": opponent,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.PARLEY,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def _resolve_opponent_stat_fields(  # noqa: PLR0913
    block: object | None,
    *,
    soak_value: int | None,
    probing_threshold: int | None,
    swarm_count: int | None,
    body_toughness: int | None,
    bodies_per_attack: int | None,
    barrier_strength: int | None,
) -> tuple[int, int | None, int | None, int | None, int | None, int | None]:
    """Return resolved (soak, probing, swarm, body_toughness, bodies_per_attack, barrier)
    from either the auto-scaling block or manual-mode defaults."""
    if block is not None:
        return (
            soak_value if soak_value is not None else block.soak_value,
            probing_threshold if probing_threshold is not None else block.probing_threshold,
            swarm_count if swarm_count is not None else block.swarm_count,
            body_toughness if body_toughness is not None else block.body_toughness,
            bodies_per_attack if bodies_per_attack is not None else block.bodies_per_attack,
            barrier_strength if barrier_strength is not None else block.barrier_strength,
        )
    return (
        soak_value if soak_value is not None else 0,
        probing_threshold,
        swarm_count,
        body_toughness,
        bodies_per_attack,
        barrier_strength,
    )


def _resolve_objectdb_for_opponent(
    encounter: CombatEncounter,
    name: str,
    persona: Persona | None,
    existing_objectdb: ObjectDB | None,
) -> tuple[object, bool]:
    """Resolve the ObjectDB and ephemeral flag for a new CombatOpponent.

    Three sources (checked in order):
    - existing_objectdb: pre-existing OD — not ephemeral, must be a Character.
    - persona: reuses persona's character OD — not ephemeral.
    - neither: creates a fresh CombatNPC in encounter.room — ephemeral.
    """
    from evennia.utils.create import create_object  # noqa: PLC0415

    from typeclasses.characters import Character  # noqa: PLC0415
    from world.combat.typeclasses.combat_npc import CombatNPC  # noqa: PLC0415

    if existing_objectdb is not None:
        if not isinstance(existing_objectdb, Character):
            msg = (
                f"existing_objectdb must be a Character typeclass instance "
                f"(got {type(existing_objectdb).__name__}). "
                f"Combat damage paths require character.conditions handler access."
            )
            raise TypeError(msg)
        return existing_objectdb, False

    if persona is not None:
        return persona.character_sheet.character, False

    if encounter.room is None:
        msg = "Cannot create ephemeral CombatNPC: encounter has no room."
        raise ValueError(msg)
    return create_object(CombatNPC, key=name, location=encounter.room, nohome=True), True


def _acting_story_for_encounter(encounter: CombatEncounter) -> Story | None:
    """The Story an ``add_opponent`` custody check acts on behalf of (#2001 Task 5).

    ``CombatEncounter.story_beat`` is set when this encounter resolves a
    specific Beat (#1760) — walking beat->episode->chapter->story mirrors
    ``custody_verdict_for_stake``'s ``stake.beat.episode.chapter.story``, so a
    GM running an encounter for the very story that protects the spawned NPC
    is never treated as "a different story". None when the encounter isn't
    wired to a beat (legacy/ad-hoc combat) — the custody seam then falls back
    to the participation/clearance rules alone.
    """
    if encounter.story_beat is None:
        return None
    return encounter.story_beat.episode.chapter.story


def _enforce_opponent_custody_gate(
    objectdb: object,
    is_ephemeral: bool,
    encounter: CombatEncounter,
    acting_account: AccountDB | None,
) -> None:
    """Custody APPEAR gate for ``add_opponent`` (#2001 Task 5).

    Gated ONLY when the opponent resolves to an EXISTING ``CharacterSheet``
    (``existing_objectdb``/``persona`` path) — a freshly-created ephemeral
    ``CombatNPC`` (``is_ephemeral`` True) has no ``CharacterSheet`` and is
    never gated. ``acting_account=None`` is the system-initiated carve-out
    (duels/cast_seed/magic-summon/companion-materialize callers pass no GM
    account) — the check is SKIPPED entirely, never called with
    ``actor_account=None`` (which inside ``check_subject_custody`` would mean
    "no clearance possible", blocking system spawns it should never touch).

    Raises:
        NPCUnderCustodyError: When ``check_subject_custody`` refuses the
            acting GM at ``CustodyScope.APPEAR``. The disclosure-safe message
            mirrors ``StakeSerializer``'s custody gate (ADR-0033 posture —
            never the protecting story's identity).
    """
    if is_ephemeral or acting_account is None:
        return
    sheet = objectdb.character_sheet
    if sheet is None:
        return

    from world.combat.scaling import NPCUnderCustodyError  # noqa: PLC0415
    from world.stories.constants import CustodyScope  # noqa: PLC0415
    from world.stories.services.custody import (  # noqa: PLC0415
        check_subject_custody,
        subject_identity_for_sheet,
    )

    verdict = check_subject_custody(
        subject_identity=subject_identity_for_sheet(sheet),
        actor_account=acting_account,
        scope=CustodyScope.APPEAR,
        acting_story=_acting_story_for_encounter(encounter),
    )
    if verdict.allowed:
        return

    if verdict.custodian_gm_username:
        msg = (
            "This NPC is under another story's custody — request clearance "
            f"from GM {verdict.custodian_gm_username}."
        )
    else:
        msg = (
            "This NPC is under another story's custody — request clearance "
            "from the story's GM via staff."
        )
    raise NPCUnderCustodyError(msg, user_message=msg)


def add_opponent(  # noqa: PLR0913 - opponent creation requires all stat fields
    encounter: CombatEncounter,
    *,
    name: str,
    tier: str,
    threat_pool: ThreatPool | None,
    max_health: int | None = None,
    description: str = "",
    soak_value: int | None = None,
    probing_threshold: int | None = None,
    swarm_count: int | None = None,
    body_toughness: int | None = None,
    bodies_per_attack: int | None = None,
    barrier_strength: int | None = None,
    auto_phases: bool = True,
    persona: Persona | None = None,
    existing_objectdb: ObjectDB | None = None,
    acting_account: AccountDB | None = None,
    position: Position | None = None,
) -> CombatOpponent:
    """Create a CombatOpponent. Three sources for the ObjectDB:

    - existing_objectdb: pre-existing OD (PvP, named NPC w/o persona). Never ephemeral.
    - persona: reuses persona's character ObjectDB. Never ephemeral.
    - neither: creates a new CombatNPC OD scoped to this encounter. Ephemeral.

    When ``max_health`` is omitted (the opt-in signal), the scaling formula
    fills in every omitted stat field via
    ``compute_opponent_stat_block(tier, encounter)``.  Passing ``max_health``
    selects manual mode: the formula is never called and other omitted stats
    keep their legacy defaults (e.g. ``soak_value`` → 0).  Explicitly-passed
    values always win over the formula.  Pass ``auto_phases=False`` to skip
    automatic ``BossPhase`` creation for BOSS-tier opponents (manual mode also
    creates no phases, since no block is computed).

    ``acting_account`` (#2001 Task 5): the GM account running this spawn, used
    ONLY for the custody APPEAR gate on an existing/persona-sourced opponent's
    CharacterSheet (see ``_enforce_opponent_custody_gate``). Left at the
    default ``None`` by every system-initiated caller (duels, cast_seed, magic
    summon effect handlers, companion materialize) — deliberately un-gated.
    Raises ``NPCUnderCustodyError`` (a ``ValueError``) when refused.

    ``position`` (#2005) places the resolved objectdb there via
    ``place_in_position`` — the unchecked staging primitive, not the validated
    voluntary-entry one — once the opponent's objectdb is known. The room match
    is validated *before* the ``CombatOpponent`` row is persisted, so a
    cross-room ``position`` raises ``PositionError`` with no saved-but-unplaced
    opponent left behind. Omitted (default) leaves the opponent unplaced,
    matching legacy behavior.
    """
    from world.combat.scaling import compute_opponent_stat_block  # noqa: PLC0415

    # The formula is triggered by an absent max_health (auto-scaling mode).
    # Callers that pass max_health explicitly are in "manual mode": omitted
    # secondary stats fall back to their legacy defaults (soak=0, etc.).
    block = compute_opponent_stat_block(tier, encounter) if max_health is None else None
    resolved_max_health: int = max_health if max_health is not None else block.max_health

    (
        resolved_soak,
        resolved_probing,
        resolved_swarm,
        resolved_body_toughness,
        resolved_bodies_per_attack,
        resolved_barrier_strength,
    ) = _resolve_opponent_stat_fields(
        block,
        soak_value=soak_value,
        probing_threshold=probing_threshold,
        swarm_count=swarm_count,
        body_toughness=body_toughness,
        bodies_per_attack=bodies_per_attack,
        barrier_strength=barrier_strength,
    )

    # Action economy: auto-scaling stamps from the tier template; manual mode
    # defaults to 1 (the legacy behavior for hand-built opponents).
    resolved_actions_per_round: int = block.actions_per_round if block is not None else 1

    objectdb, is_ephemeral = _resolve_objectdb_for_opponent(
        encounter, name, persona, existing_objectdb
    )
    _enforce_opponent_custody_gate(objectdb, is_ephemeral, encounter, acting_account)

    if position is not None and position.room_id != objectdb.db_location_id:
        # Validate the room match before persisting the CombatOpponent row below —
        # the resolved objectdb is known now, so a bad position fails fast instead
        # of leaving a saved-but-unplaced opponent behind a failure ActionResult
        # (Task 4 fold-in, #2005). The post-save place_in_position call further
        # down re-checks the identical invariant; it can no longer fail once
        # execution reaches it.
        from world.areas.positioning.exceptions import PositionError  # noqa: PLC0415

        msg = "That position is not in the same room as the opponent."
        raise PositionError(msg)

    opp = CombatOpponent(
        encounter=encounter,
        name=name,
        tier=tier,
        max_health=resolved_max_health,
        health=resolved_max_health,
        threat_pool=threat_pool,
        description=description,
        soak_value=resolved_soak,
        probing_threshold=resolved_probing,
        swarm_count=resolved_swarm,
        # Bodies-at-start mirrors the initial count so a percentage-remaining
        # display has a denominator; null for non-swarm tiers (resolved_swarm None).
        max_swarm_count=resolved_swarm,
        body_toughness=resolved_body_toughness,
        bodies_per_attack=resolved_bodies_per_attack,
        barrier_strength=resolved_barrier_strength,
        actions_per_round=resolved_actions_per_round,
        persona=persona,
        objectdb=objectdb,
        objectdb_is_ephemeral=is_ephemeral,
    )
    opp.full_clean()
    opp.save()

    if position is not None:
        from typing import cast  # noqa: PLC0415

        from world.areas.positioning.services import place_in_position  # noqa: PLC0415

        # _resolve_objectdb_for_opponent is annotated tuple[object, bool];
        # every branch actually returns an ObjectDB (Character or CombatNPC).
        place_in_position(cast("ObjectDB", objectdb), position)

    # --- Auto-generate BossPhase rows from the computed block ---
    if tier == OpponentTier.BOSS and auto_phases and block is not None and block.phases:
        BossPhase.objects.bulk_create(
            [
                BossPhase(
                    opponent=opp,
                    phase_number=spec.phase_number,
                    health_trigger_percentage=spec.health_trigger_percentage,
                    soak_value=spec.soak_value,
                    probing_threshold=spec.probing_threshold,
                    threat_pool=None,
                )
                for spec in block.phases
            ]
        )

    from world.combat.escalation import check_hated_foe_surges_for_new_opponent  # noqa: PLC0415

    check_hated_foe_surges_for_new_opponent(opp)

    return opp


def spawn_from_creature_template(
    encounter: CombatEncounter,
    template: CreatureTemplate,
    *,
    position: Position | None = None,
    acting_account: AccountDB | None = None,
) -> CombatOpponent:
    """Spawn a CombatOpponent from a CreatureTemplate bestiary entry (#2016).

    Thin wrapper over add_opponent. Clones CreaturePhaseTemplate rows into
    BossPhase rows on the spawned opponent if present. Stamps break-bar
    config and vulnerability fields from BreakBarConfig.
    """
    from world.combat.models import CreaturePhaseTemplate  # noqa: PLC0415

    has_authored_phases = CreaturePhaseTemplate.objects.filter(creature_template=template).exists()

    opp = add_opponent(
        encounter,
        name=template.name,
        tier=template.tier,
        threat_pool=template.threat_pool,
        soak_value=template.soak_override,
        probing_threshold=template.probing_override,
        auto_phases=not has_authored_phases,
        position=position,
        acting_account=acting_account,
    )

    if has_authored_phases:
        _clone_authored_phases(encounter, opp, template)

    return opp


def _clone_authored_phases(
    encounter: CombatEncounter,
    opp: CombatOpponent,
    template: CreatureTemplate,
) -> None:
    """Clone CreaturePhaseTemplate rows into BossPhase rows and stamp break-bar config."""
    from world.combat.models import CreaturePhaseTemplate  # noqa: PLC0415
    from world.combat.scaling import (  # noqa: PLC0415
        compute_party_multiplier,
        compute_party_profile,
    )

    phase_templates = CreaturePhaseTemplate.objects.filter(creature_template=template).order_by(
        "phase_number"
    )
    BossPhase.objects.filter(opponent=opp).delete()

    profile = compute_party_profile(encounter)
    party_mult = compute_party_multiplier(profile.party_size, profile.avg_level)

    for pt in phase_templates:
        phase = BossPhase.objects.create(
            opponent=opp,
            phase_number=pt.phase_number,
            threat_pool=pt.threat_pool,
            soak_value=pt.soak_value,
            probing_threshold=pt.probing_threshold,
            health_trigger_percentage=pt.health_trigger_percentage,
            description=pt.description,
            actions_per_round=pt.actions_per_round,
            damage_multiplier=pt.damage_multiplier,
            extra_actions=pt.extra_actions,
            reinforcement_template=pt.reinforcement_template,
            reinforcement_count=pt.reinforcement_count,
        )
        if hasattr(pt, "break_bar"):
            _stamp_phase_break_bar_config(phase, pt.break_bar, party_mult, opp, pt.phase_number)


def minimum_break_bar_threshold() -> int:
    """Pacing floor for a boss's break-bar threshold (#2642, batch-3 F-7a).

    ``(soulfray_stage_count + PACING_FLOOR_ROUND_PADDING) * BAR_UNITS_PER_ROUND`` —
    ensures the anima -> Soulfray -> audere arc has room to play out before the
    wall breaks (median 6-8 rounds, tail ~10). Returns 0 (no clamp) when Soulfray
    has not been authored yet (stage_count == 0) — a bare/test DB should not be
    forced onto a floor derived from unauthored content.
    """
    from world.conditions.models import ConditionStage  # noqa: PLC0415
    from world.magic.audere import SOULFRAY_CONDITION_NAME  # noqa: PLC0415

    stage_count = ConditionStage.objects.filter(condition__name=SOULFRAY_CONDITION_NAME).count()
    if stage_count == 0:
        return 0
    return (stage_count + PACING_FLOOR_ROUND_PADDING) * BAR_UNITS_PER_ROUND


def _stamp_phase_break_bar_config(
    phase: BossPhase,
    config: object,
    party_mult: Decimal,
    opp: CombatOpponent,
    phase_number: int,
) -> None:
    """Stamp BreakBarConfig values onto a BossPhase (and onto the opponent for phase 1)."""
    authored_threshold = round(Decimal(config.max_threshold) * party_mult)
    threshold = max(authored_threshold, minimum_break_bar_threshold())
    phase.break_bar_threshold = threshold
    phase.vulnerability_rounds = config.vulnerability_rounds
    phase.vulnerability_intensity_bonus = config.intensity_bonus
    phase.save(
        update_fields=[
            "break_bar_threshold",
            "vulnerability_rounds",
            "vulnerability_intensity_bonus",
        ]
    )
    if phase_number == 1:
        opp.break_bar_threshold = threshold
        opp.break_bar_current = threshold
        opp.vulnerability_rounds = config.vulnerability_rounds
        opp.vulnerability_intensity_bonus = config.intensity_bonus
        opp.save(
            update_fields=[
                "break_bar_threshold",
                "break_bar_current",
                "vulnerability_rounds",
                "vulnerability_intensity_bonus",
            ]
        )


def _bulk_primary_levels(char_ids: list[int]) -> dict[int, int]:
    """Return {character_id: level} for each id in *char_ids* using at most two queries.

    Mirrors the fallback chain in ``get_character_path_level``:
    primary row → highest row → 1.  Characters with no CharacterClassLevel at
    all are omitted from the dict (callers use ``.get(cid, 1)`` for the final
    fallback).
    """
    from world.classes.models import CharacterClassLevel  # noqa: PLC0415

    level_map: dict[int, int] = dict(
        CharacterClassLevel.objects.filter(
            character_id__in=char_ids,
            is_primary=True,
        ).values_list("character_id", "level")
    )

    without_primary = [cid for cid in char_ids if cid not in level_map]
    if without_primary:
        seen: set[int] = set()
        for char_id, lvl in (
            CharacterClassLevel.objects.filter(character_id__in=without_primary)
            .order_by("character_id", "-level")
            .values_list("character_id", "level")
        ):
            if char_id not in seen:
                level_map[char_id] = lvl
                seen.add(char_id)
    return level_map


def _dissolve_graduated_bonds(enc: CombatEncounter) -> None:
    """Dissolve any MentorBond that has graduated for ACTIVE participants in *enc*.

    A bond is "graduated" when the adjusted party's raw primary level is now
    within the covenant band — the bond is mechanically inactive and should be
    persisted as dissolved so future reads skip it cleanly.

    Write-safe: called only from ``begin_declaration_phase`` (encounter start).
    No per-bond queries: bulk-fetches bonds in one query, resolves primary levels
    for all adjusted-party characters in a second bulk query, then determines
    graduation inline — O(1) queries regardless of graduated-bond count.
    """
    from world.covenants.constants import MentorBondAdjusted  # noqa: PLC0415
    from world.covenants.mentorship import dissolve_mentor_bond, is_in_band  # noqa: PLC0415
    from world.covenants.models import MentorBond  # noqa: PLC0415

    sheet_ids = list(
        CombatParticipant.objects.filter(
            encounter=enc,
            status=ParticipantStatus.ACTIVE,
        ).values_list("character_sheet_id", flat=True)
    )
    if not sheet_ids:
        return

    # One bulk query: all active bonds where any participant is either the
    # mentor or the sidekick side. Resolve covenant + both character FKs so
    # no per-bond queries are needed below.
    active_bonds = list(
        MentorBond.objects.active()
        .filter(Q(mentor_sheet_id__in=sheet_ids) | Q(sidekick_sheet_id__in=sheet_ids))
        .select_related(
            "covenant",
            "mentor_sheet__character",
            "sidekick_sheet__character",
        )
    )
    if not active_bonds:
        return

    # Collect the adjusted-party character id for each bond (one id per bond).
    adjusted_char_ids = [
        bond.sidekick_sheet.character_id
        if bond.adjusted_party == MentorBondAdjusted.SIDEKICK
        else bond.mentor_sheet.character_id
        for bond in active_bonds
    ]

    # Two bulk queries at most: primary levels + highest-level fallback.
    level_map = _bulk_primary_levels(adjusted_char_ids)

    for bond, char_id in zip(active_bonds, adjusted_char_ids, strict=True):
        raw = level_map.get(char_id, 1)
        if is_in_band(bond.covenant, raw):
            dissolve_mentor_bond(bond)


@transaction.atomic
def begin_declaration_phase(encounter: CombatEncounter) -> None:
    """Advance round_number by 1 and set status to DECLARING.

    Uses select_for_update to prevent concurrent calls.
    Raises ValueError if the encounter is not BETWEEN_ROUNDS.
    """
    enc = CombatEncounter.objects.select_for_update().get(pk=encounter.pk)
    if enc.status != RoundStatus.BETWEEN_ROUNDS:
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

    # Belt-and-suspenders: reject a lethal PvP duel before declaration advances.
    if enc.encounter_type == EncounterType.DUEL:
        from world.combat.duels import assert_duel_lethality_valid  # noqa: PLC0415

        assert_duel_lethality_valid(enc)

    enc.round_number += 1
    enc.status = RoundStatus.DECLARING
    enc.round_started_at = timezone.now()
    enc.save(update_fields=["round_number", "status", "round_started_at"])

    # Reaction economy (#2639): every participant's reaction budget refills
    # each round. A raw queryset .update() would bypass the SharedMemoryModel
    # identity map — any already-cached CombatParticipant instance (e.g. one
    # a caller is still holding) would keep reading its stale pre-reset value
    # forever, since refresh_from_db() on an idmapper model returns the SAME
    # cached instance rather than re-hydrating it from the row. Mutate the
    # identity-mapped instances directly, then persist with one bulk_update
    # query — correct in-memory state AND a single query, not a per-
    # participant save() loop.
    reset_participants = list(CombatParticipant.objects.filter(encounter=enc))
    for reset_participant in reset_participants:
        reset_participant.reactions_used = 0
    if reset_participants:
        CombatParticipant.objects.bulk_update(reset_participants, ["reactions_used"])

    # --- Round-start per-participant upkeep: DoT tick + engagement ensure ---
    from world.vitals.services import tick_round_for_targets  # noqa: PLC0415

    active_participants_start = CombatParticipant.objects.filter(
        encounter=enc,
        status=ParticipantStatus.ACTIVE,
    ).select_related("character_sheet__character")
    active_opponents_start = CombatOpponent.objects.filter(
        encounter=enc,
        status=OpponentStatus.ACTIVE,
    ).select_related("objectdb")
    start_targets = [p.character_sheet.character for p in active_participants_start]
    start_targets += [opp.objectdb for opp in active_opponents_start if opp.objectdb is not None]
    tick_round_for_targets(start_targets, timing="start")

    for p in active_participants_start:
        # Permanent idempotency safety net: any participant that reached this
        # point without a combat engagement (however they were created) gets
        # one ensured here so all downstream engagement-dependent paths are safe.
        _ensure_combat_engagement(p)

    # --- Escalation tick (#872): opted-in encounters build pressure each round ---
    from world.combat.escalation import (  # noqa: PLC0415
        apply_escalation_tick,
        install_escalation_room_triggers,
    )

    if enc.escalation_curve is not None:
        install_escalation_room_triggers(enc)
        apply_escalation_tick(enc)

    # --- Mentor's Vow (#1165): persist graduated bond dissolution at round start ---
    # Bonds that have graduated (adjusted party leveled into band) are dissolved
    # here so future reads via effective_combat_level skip them cleanly.
    _dissolve_graduated_bonds(enc)

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


def _validate_technique_reach(
    participant: CombatParticipant,
    focused_action: Technique,
    *,
    focused_opponent_target: CombatOpponent | None,
    focused_ally_target: CombatParticipant | None,
) -> None:
    """Raise ValueError if the technique's reach cannot cover the declared target.

    Resolves the target's ObjectDB from either ``focused_opponent_target.objectdb``
    (for NPC/opponent targets) or ``focused_ally_target.character_sheet.character``
    (for participant/ally targets). Delegates to ``technique_can_reach``, which is
    lenient when either combatant is unpositioned.

    Only runs when a target is actually provided; skips self/no-target declarations.
    """
    from world.combat.reach import technique_can_reach  # noqa: PLC0415

    attacker_objectdb = participant.character_sheet.character

    target_objectdb = None
    if focused_opponent_target is not None:
        target_objectdb = focused_opponent_target.objectdb
    elif focused_ally_target is not None and focused_ally_target != participant:
        target_objectdb = focused_ally_target.character_sheet.character

    if target_objectdb is None:
        # No external target (self-buff or no target) — reach is not constraining.
        return

    if not technique_can_reach(attacker_objectdb, focused_action, target_objectdb):
        from actions.errors import ActionDispatchError  # noqa: PLC0415

        raise ActionDispatchError(ActionDispatchError.TARGET_OUT_OF_REACH)


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
    confirm_soulfray_risk: bool = False,
    fury_commitment: FuryTier | None = None,
    fury_anchor: CharacterSheet | None = None,
    cast_destination: Position | None = None,
    cast_position_a: Position | None = None,
    cast_position_b: Position | None = None,
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

    ``cast_destination``/``cast_position_a``/``cast_position_b`` are pre-validated
    (see ``resolve_cast_position_params``, #2206) — this function only persists them.

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
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot declare action: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    # Lethal-duel risk-acknowledgement gate (#568 Task 12b). A PC placed into a
    # lethal DUEL by create_lethal_duel is deliberately not auto-acknowledged, and
    # the #777 outsider gate does not cover an already-active participant — so block
    # declaration until an EncounterRiskAcknowledgement exists. Scoped to DUEL only:
    # lethal party-combat PCs self-join via join_encounter (which records an ack),
    # and GM-placed party-combat PCs (add_participant, no ack) must not be blocked.
    if encounter.encounter_type == EncounterType.DUEL and encounter.is_lethal:
        has_ack = EncounterRiskAcknowledgement.objects.filter(
            encounter=encounter,
            character_sheet=participant.character_sheet,
        ).exists()
        if not has_ack:
            msg = "You must acknowledge the lethal risk of this duel before acting."
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

    # Positional reach gate: enforce technique.reach against the declared target.
    # Only fires when there is a technique and a resolved target. Lenient when
    # either combatant is unpositioned (technique_can_reach returns True).
    if focused_action is not None:
        _validate_technique_reach(
            participant,
            focused_action,
            focused_opponent_target=focused_opponent_target,
            focused_ally_target=focused_ally_target,
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
            "confirm_soulfray_risk": confirm_soulfray_risk,
            "fury_commitment": fury_commitment,
            "fury_anchor": fury_anchor,
            "cast_destination": cast_destination,
            "cast_position_a": cast_position_a,
            "cast_position_b": cast_position_b,
        },
    )
    return action


def _equipped_weapon_archetype(character: Character) -> str | None:
    """The ``gear_archetype`` of character's strongest equipped weapon, or None."""
    inst = _select_equipped_weapon(character)
    if inst is None:
        return None
    return inst.template.gear_archetype


def declare_charge(
    participant: CombatParticipant,
    technique: Technique,
    opponent: CombatOpponent,
) -> CombatRoundAction:
    """Declare a mounted charge — closes distance to *opponent*, then attacks (#1843).

    Validations:
    - Participant must be able to act and the encounter must be DECLARING.
    - The rider must hold the Mounted condition
      (``world.companions.mount_content.MOUNTED_CONDITION_NAME``).
    - *opponent* must be ACTIVE.
    - *opponent*'s position must be at least 1 hop from the rider's current
      position AND reachable within ``CHARGE_MAX_HOPS``. Lenient (allowed)
      when either combatant is unpositioned — mirrors
      ``technique_can_reach``'s leniency (``world/combat/reach.py``).

    Resolution (``_resolve_pc_action``) moves the rider onto *opponent*'s
    position (``force_move_to_position``), then falls through to the normal
    weapon-attack pipeline — ``CombatTechniqueResolver`` folds
    ``CHARGE_CHECK_BONUS``/``CHARGE_DAMAGE_BONUS`` into the check/damage
    (doubled when the equipped weapon is a LANCE). The attack always runs
    through the normal (non-bypassing) damage pipeline — defenses, guardians,
    and ramparts fire exactly as they would for any other attack.

    Raises ValueError with clear messages for validation failures.
    """
    from world.areas.positioning.services import position_of, position_reachable  # noqa: PLC0415
    from world.companions.mount_content import MOUNTED_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import has_condition  # noqa: PLC0415
    from world.magic.constants import TechniqueReach  # noqa: PLC0415
    from world.vitals.services import can_act  # noqa: PLC0415

    encounter = participant.encounter
    if not can_act(participant.character_sheet):
        msg = "Cannot charge: character is dead or incapacitated."
        raise ValueError(msg)
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot charge: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)
    if opponent.status != OpponentStatus.ACTIVE:
        msg = "Cannot charge a defeated opponent."
        raise ValueError(msg)

    mounted_template = ConditionTemplate.get_by_name(MOUNTED_CONDITION_NAME)
    if not has_condition(participant.character_sheet.character, mounted_template):
        msg = "Cannot charge: you must be mounted."
        raise ValueError(msg)

    rider_pos = position_of(participant.character_sheet.character)
    target_pos = position_of(opponent.objectdb) if opponent.objectdb is not None else None
    if rider_pos is not None and target_pos is not None:
        if rider_pos.pk == target_pos.pk:
            msg = "Cannot charge: the target is already within reach."
            raise ValueError(msg)
        if not position_reachable(
            rider_pos, target_pos, TechniqueReach.REACH_N, reach_hops=CHARGE_MAX_HOPS
        ):
            msg = "Cannot charge: the target is not reachable."
            raise ValueError(msg)

    action, _created = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": technique,
            "focused_category": technique.action_category,
            "effort_level": EffortLevel.MEDIUM,
            "focused_opponent_target": opponent,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.CHARGE,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": False,
        },
    )
    return action


_JOUST_PARTICIPANT_COUNT = 2  # jousts are strictly 1v1 DUEL encounters


def declare_joust(
    participant: CombatParticipant,
    technique: Technique,
) -> CombatRoundAction:
    """Declare a joust — a mounted, lance-armed opposed pass (#1843).

    Only declarable in a DUEL encounter with exactly two participants where
    BOTH duelists currently hold the Mounted condition and have a
    LANCE-archetype weapon equipped. Resolution
    (``_resolve_joust_pass``, dispatched from ``_resolve_pc_action`` once both
    sides have declared JOUST) rolls one opposed weapon-attack check per side
    and grades the outcome by the success_level gap into
    ``JOUST_DECISIVE_MARGIN``/``JOUST_NARROW_MARGIN`` bands.

    Raises ValueError with clear messages for validation failures.
    """
    from world.companions.mount_content import MOUNTED_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import has_condition  # noqa: PLC0415
    from world.items.constants import GearArchetype  # noqa: PLC0415
    from world.vitals.services import can_act  # noqa: PLC0415

    encounter = participant.encounter
    if not can_act(participant.character_sheet):
        msg = "Cannot joust: character is dead or incapacitated."
        raise ValueError(msg)
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot joust: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)
    if encounter.encounter_type != EncounterType.DUEL:
        msg = "Cannot joust: only valid in a duel."
        raise ValueError(msg)

    other = (
        CombatParticipant.objects.filter(encounter=encounter)
        .exclude(pk=participant.pk)
        .select_related("character_sheet")
        .first()
    )
    if other is None or encounter.participants.count() != _JOUST_PARTICIPANT_COUNT:
        msg = "Cannot joust: requires exactly two duelists."
        raise ValueError(msg)

    mounted_template = ConditionTemplate.get_by_name(MOUNTED_CONDITION_NAME)
    for combatant in (participant, other):
        if not has_condition(combatant.character_sheet.character, mounted_template):
            msg = "Cannot joust: both duelists must be mounted."
            raise ValueError(msg)
        if _equipped_weapon_archetype(combatant.character_sheet.character) != GearArchetype.LANCE:
            msg = "Cannot joust: both duelists must wield a lance."
            raise ValueError(msg)

    action, _created = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": technique,
            "focused_category": technique.action_category,
            "effort_level": EffortLevel.MEDIUM,
            "focused_opponent_target": None,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.JOUST,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": False,
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
    # Falter: skip entries that require a steady nerve (#2015).
    from world.combat.morale import (  # noqa: PLC0415
        OpponentMoraleState,
        morale_state_for,
    )

    faltering = morale_state_for(opponent) == OpponentMoraleState.FALTER

    for entry in entries:
        # Falter: skip requires_steady entries (designers author "weakened" entries).
        if faltering and entry.requires_steady:
            continue

        # Filter by minimum_phase
        if entry.minimum_phase is not None and entry.minimum_phase > opponent.current_phase:
            continue

        # Filter by cooldown — check against pre-fetched set
        if entry.cooldown_rounds is not None and entry.pk in cooldown_used_entry_ids:
            continue

        eligible.append(entry)

    return eligible


_TargetT = TypeVar("_TargetT")


def _select_targets_core(  # noqa: PLR0911
    entry: ThreatPoolEntry,
    candidates: list[_TargetT],
    health_of: Callable[[list[_TargetT]], list[int]],
    rotation: int = 0,
    *,
    _threat_map: dict[int, int] | None = None,
    _shield_participant_ids: set[int] | None = None,
) -> list[_TargetT]:
    """Shared targeting-mode selector for participants and opponents (#1584).

    One algorithm (ALL / MULTI / RANDOM / LOWEST_HEALTH / HIGHEST_THREAT /
    SPECIFIC_ROLE / rotated-default) drives both the participant ``targets``
    path and the opponent ``opponent_targets`` path (ADR-0016 — no parallel
    selector).

    ``health_of`` returns health values parallel to ``candidates`` and is only
    invoked for the LOWEST_HEALTH mode, so participants keep their single batch
    query and opponents read ``.health`` directly.

    ``_threat_map`` and ``_shield_participant_ids`` are pre-computed by
    ``select_npc_actions`` for HIGHEST_THREAT / SPECIFIC_ROLE modes (#2020).
    They map candidate PKs to threat values and identify SHIELD-axis PCs (blend
    weight > 0).

    ``rotation`` offsets the deterministic (non-random, non-health-sorted)
    selection so a swarm's successive attacks fan across distinct targets rather
    than dogpiling the first one (#983). It is a no-op for the ALL, RANDOM, and
    LOWEST_HEALTH modes, which already spread across or intentionally focus on
    their own terms.
    """
    if not candidates:
        return []

    mode = entry.targeting_mode
    selection = entry.target_selection

    if mode == TargetingMode.ALL:
        return list(candidates)

    count = 1
    if mode == TargetingMode.MULTI:
        count = entry.target_count or 1

    count = min(count, len(candidates))

    if selection == TargetSelection.LOWEST_HEALTH:
        healths = health_of(candidates)
        sorted_by_health = [
            c
            for _, c in sorted(
                zip(healths, candidates, strict=True),
                key=lambda pair: pair[0],
            )
        ]
        return sorted_by_health[:count]

    if selection == TargetSelection.RANDOM:
        return random.sample(candidates, count)  # NOSONAR game RNG (combat targeting), not crypto

    # HIGHEST_THREAT: sort candidates by ThreatRecord.threat_value desc (#2020).
    # Falls back to rotated order when no threat records exist (pre-threat
    # encounters or mooks with no damage yet).
    if selection == TargetSelection.HIGHEST_THREAT and _threat_map:
        sorted_by_threat = sorted(
            candidates,
            key=lambda c: _threat_map.get(c.pk, 0),
            reverse=True,
        )
        return sorted_by_threat[:count]

    # SPECIFIC_ROLE: prioritize SHIELD-axis (defense) PCs, then break ties
    # by highest threat (#2020). Falls back to highest-threat-only (or rotated)
    # when no SHIELD-axis PC is present.
    if selection == TargetSelection.SPECIFIC_ROLE and _shield_participant_ids:
        shielded = [c for c in candidates if c.pk in _shield_participant_ids]
        if shielded:
            if _threat_map:
                shielded.sort(
                    key=lambda c: _threat_map.get(c.pk, 0),
                    reverse=True,
                )
            return shielded[:count]

    # Default: rotated DB order (no threat data available).
    offset = rotation % len(candidates)
    rotated = candidates[offset:] + candidates[:offset]
    return list(rotated[:count])


def _select_targets(
    entry: ThreatPoolEntry,
    active_participants: list[CombatParticipant],
    rotation: int = 0,
    *,
    _threat_map: dict[int, int] | None = None,
    _shield_participant_ids: set[int] | None = None,
) -> list[CombatParticipant]:
    """Select participant targets for a threat pool entry (typed wrapper)."""

    def _participant_healths(candidates: list[CombatParticipant]) -> list[int]:
        from world.vitals.models import CharacterVitals  # noqa: PLC0415

        sheet_ids = [p.character_sheet_id for p in candidates]
        health_map = dict(
            CharacterVitals.objects.filter(
                character_sheet_id__in=sheet_ids,
            ).values_list("character_sheet_id", "health")
        )
        return [health_map.get(p.character_sheet_id, 0) for p in candidates]

    return _select_targets_core(
        entry,
        active_participants,
        _participant_healths,
        rotation,
        _threat_map=_threat_map,
        _shield_participant_ids=_shield_participant_ids,
    )


def _select_opponent_targets(
    entry: ThreatPoolEntry,
    active_opponents: list[CombatOpponent],
    rotation: int = 0,
    *,
    _threat_map: dict[int, int] | None = None,
    _shield_participant_ids: set[int] | None = None,
) -> list[CombatOpponent]:
    """Select opponent targets for a threat pool entry (typed wrapper, #1584).

    Routes an ALLY summon's attack at ENEMY opponents; opponents carry health on
    the row, so no batch query is needed.
    """
    return _select_targets_core(
        entry,
        active_opponents,
        lambda opps: [o.health for o in opps],
        rotation,
        _threat_map=_threat_map,
        _shield_participant_ids=_shield_participant_ids,
    )


def _exclude_charmers_party(
    opponent: CombatOpponent, participants: list[CombatParticipant]
) -> list[CombatParticipant]:
    """Return ``participants`` minus the charm source's party (#1590).

    The charmer is the ``source_character`` on the opponent's active Charm
    condition. If it resolves to an active ``CombatParticipant``, exclude it.
    MVP: parties are 1:1 with participants (no party grouping yet), so we
    exclude the single charmer participant. If the source is unresolvable
    (no ``source_character`` on the Charm, or the charmer left the encounter),
    the charmed NPC has no party to fight for — returning ``[]`` so the caller
    skips the round is intentional (NOT a fall-back to ENEMY: a charmed NPC
    must never attack the charmer's side even if the charmer is gone).
    """
    from world.conditions.constants import CHARM_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.services import get_active_conditions  # noqa: PLC0415

    if opponent.objectdb_id is None:
        return participants
    charmer_pk = None
    for inst in get_active_conditions(opponent.objectdb):
        if inst.condition.name == CHARM_CONDITION_NAME and inst.source_character_id is not None:
            charmer_pk = inst.source_character_id
            break
    if charmer_pk is None:
        return []
    return [p for p in participants if p.character_sheet.character_id != charmer_pk]


def _get_opponent_targets(
    opponent: CombatOpponent,
    active_participants: list[CombatParticipant],
    encounter: CombatEncounter,
) -> list[CombatParticipant]:
    """Return the PCs an NPC is allowed to target after consulting allegiance.

    Calm (``NEUTRAL``) returns an empty list so the NPC skips the round.
    Charm (``ALLY_OF_CASTER``) excludes the charmer's party. Everything else
    returns the full active participant list (#1590).
    """
    from world.npc_services.allegiance import derive_allegiance  # noqa: PLC0415

    allegiance = derive_allegiance(opponent, encounter)
    if allegiance == Allegiance.NEUTRAL:
        return []
    if allegiance == Allegiance.ALLY_OF_CASTER:
        return _exclude_charmers_party(opponent, list(active_participants))
    return list(active_participants)


def _batch_fetch_cooldown_data(
    opponents: list[CombatOpponent],
    entries_by_pool: dict[int, list[ThreatPoolEntry]],
    all_entries: list[ThreatPoolEntry],
    round_number: int,
) -> dict[int, set[int]]:
    """Batch-fetch recently-used entry IDs per opponent for cooldown checks.

    Returns a mapping of opponent_id -> set of entry IDs that are on cooldown.

    #2637: a wind-up entry is committed at DECLARATION, not maturation — it
    does not get a CombatOpponentAction row until it matures rounds later, so
    a pending PendingOpponentAttack's declared_round also counts as "used"
    for cooldown purposes. Batched identically to the CombatOpponentAction
    read below (one extra fixed query, never a query per opponent).
    """
    cooldown_filters = Q()
    pending_cooldown_filters = Q()
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
        pending_cooldown_filters |= Q(
            opponent=opponent,
            threat_entry_id__in=cooldown_entry_ids,
            declared_round__gte=earliest_allowed,
        )

    result: dict[int, set[int]] = defaultdict(set)
    if not cooldown_filters:
        return result

    entry_cooldown_map = {
        e.pk: e.cooldown_rounds for e in all_entries if e.cooldown_rounds is not None
    }

    recent_actions = CombatOpponentAction.objects.filter(cooldown_filters).values_list(
        "opponent_id", "threat_entry_id", "round_number"
    )
    for opp_id, entry_id, round_num in recent_actions:
        cooldown = entry_cooldown_map.get(entry_id)
        if cooldown is not None:
            earliest = max(1, round_number - cooldown + 1)
            if round_num >= earliest:
                result[opp_id].add(entry_id)

    recent_pending = PendingOpponentAttack.objects.filter(pending_cooldown_filters).values_list(
        "opponent_id", "threat_entry_id", "declared_round"
    )
    for opp_id, entry_id, round_num in recent_pending:
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
    entry from eligible threat pool entries and assigns targets. Targeting is
    allegiance-aware (#1590, ADR-0058): a charmed opponent (``ALLY_OF_CASTER``)
    skips the charmer's party, and a calmed opponent (``NEUTRAL``) holds and
    takes no action; an opponent left with no valid targets skips the round.

    Raises ValueError if the encounter is not in DECLARING status.
    """
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot select NPC actions: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    # Auto-lock formation: check threat thresholds before NPC targeting (#2020).
    from world.combat.engagement_locks import check_auto_lock_formation  # noqa: PLC0415

    check_auto_lock_formation(encounter)

    opponents = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
        )
        .exclude(threat_pool__isnull=True)
        .exclude(mirrors_participant_id__isnull=False)
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
    # Intangible PCs (incorporeal, sunk, phased) are also excluded (#1584 Task 8).
    from world.conditions.services import is_untargetable  # noqa: PLC0415
    from world.vitals.services import can_act  # noqa: PLC0415

    candidate_participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        ).select_related("character_sheet__character")
    )
    active_participants = [
        p
        for p in candidate_participants
        if can_act(p.character_sheet) and not is_untargetable(p.character_sheet.character)
    ]

    # Batch-prefetch ThreatRecord data for HIGHEST_THREAT/SPECIFIC_ROLE (#2020)
    active_participant_ids = [p.pk for p in active_participants]
    threat_maps: dict[int, dict[int, int]] = defaultdict(dict)
    if active_participant_ids:
        for tr in ThreatRecord.objects.filter(
            opponent__in=opponents,
            participant_id__in=active_participant_ids,
        ):
            threat_maps[tr.opponent_id][tr.participant_id] = tr.threat_value

    # Batch-prefetch active EngagementLocks for lock narrowing (#2020)
    active_locks_by_opponent: dict[int, int] = {}
    for lock in EngagementLock.objects.filter(
        encounter=encounter,
        opponent__in=opponents,
        status=EngagementLockStatus.ACTIVE,
    ).values("opponent_id", "participant_id"):
        active_locks_by_opponent[lock["opponent_id"]] = lock["participant_id"]

    # Batch-prefetch SHIELD-axis (blend weight > 0) participant IDs for SPECIFIC_ROLE (#2020)
    from world.covenants.constants import RoleArchetype  # noqa: PLC0415
    from world.covenants.services import precedence_role_for_combat  # noqa: PLC0415

    shield_participant_ids: set[int] = set()
    for p in active_participants:
        role = precedence_role_for_combat(p.character_sheet)
        if role is not None and role.blend_weight_for(RoleArchetype.SHIELD) > 0:
            shield_participant_ids.add(p.pk)

    actions: list[CombatOpponentAction] = []

    for opponent in opponents:
        pool_entries = entries_by_pool.get(opponent.threat_pool_id, [])
        cooldown_used = recently_used_by_opponent.get(opponent.pk, set())
        actions.extend(
            _build_opponent_round_actions(
                opponent,
                pool_entries,
                cooldown_used,
                active_participants,
                encounter,
                threat_map=threat_maps.get(opponent.pk),
                shield_participant_ids=shield_participant_ids,
                locked_participant_id=active_locks_by_opponent.get(opponent.pk),
            )
        )

    return actions


def _get_companion_order(opponent: CombatOpponent, round_number: int) -> object | None:
    """Fetch the CompanionOrder for an ALLY summon this round, if any (#1921).

    Returns None for non-summons or when no order exists.
    """
    if opponent.summoned_by_id is None or opponent.allegiance != CombatAllegiance.ALLY:
        return None

    from world.companions.models import Companion, CompanionOrder  # noqa: PLC0415

    try:
        companion = Companion.objects.get(
            owner_id=opponent.summoned_by_id,
            released_at__isnull=True,
        )
    except (Companion.DoesNotExist, Companion.MultipleObjectsReturned):
        return None

    return CompanionOrder.objects.filter(
        companion=companion,
        encounter=opponent.encounter,
        round_number=round_number,
    ).first()


def _build_opponent_round_actions(  # noqa: C901, PLR0912, PLR0913
    opponent: CombatOpponent,
    pool_entries: list[ThreatPoolEntry],
    cooldown_used: set[int],
    active_participants: list[CombatParticipant],
    encounter: CombatEncounter,
    *,
    threat_map: dict[int, int] | None = None,
    shield_participant_ids: set[int] | None = None,
    locked_participant_id: int | None = None,
) -> list[CombatOpponentAction]:
    """Create one opponent's NPC action rows for the current round.

    Returns the created actions, or an empty list when the opponent skips the
    round — no eligible (off-cooldown) threat entry, or the empty-pool guard:
    no valid target (a #1584 ALLY summon with no live enemy, or a #1590
    calmed/neutral opponent whose threat-read yielded no PCs).
    """
    from world.combat.morale import (  # noqa: PLC0415
        OpponentMoraleState,
        morale_state_for,
    )

    # Break: a broken opponent flees — set FLED and skip the round (#2015).
    if morale_state_for(opponent) == OpponentMoraleState.BREAK:
        opponent.status = OpponentStatus.FLED
        opponent.save(update_fields=["status"])
        return []

    eligible = _get_eligible_entries(opponent, pool_entries, cooldown_used)
    if not eligible:
        return []

    target_pool, targeting_participants = _npc_action_target_pool(
        opponent, active_participants, encounter
    )
    if not target_pool:
        return []

    # Lock narrowing: if an active EngagementLock exists, narrow to the locked PC (#2020).
    if locked_participant_id is not None and targeting_participants:
        locked_pool = [p for p in target_pool if p.pk == locked_participant_id]
        if locked_pool:
            target_pool = locked_pool

    # --- Companion order integration (#1921) ---
    # An ALLY summon with a CompanionOrder may override its target or skip.
    companion_order = _get_companion_order(opponent, encounter.round_number)
    if companion_order is not None:
        from world.companions.constants import CompanionOrderKind  # noqa: PLC0415

        if companion_order.order_kind == CompanionOrderKind.HOLD:
            return []  # HOLD: skip this round

        if (
            companion_order.order_kind == CompanionOrderKind.ATTACK_TARGET
            and companion_order.target_opponent_id is not None
        ):
            # Filter the pool to just the directed target (if still alive)
            directed = [opp for opp in target_pool if opp.pk == companion_order.target_opponent_id]
            if directed:
                target_pool = directed
            # else: target is dead/gone, fall back to auto-selection

    if opponent.tier == OpponentTier.SWARM and opponent.swarm_count is not None:
        n_attacks = swarm_attack_count(
            opponent.swarm_count,
            opponent.bodies_per_attack or 1,
            len(target_pool),
        )
    else:
        n_attacks = opponent.actions_per_round

    actions: list[CombatOpponentAction] = []
    for attack_index in range(n_attacks):
        weights = [e.weight for e in eligible]
        chosen = random.choices(eligible, weights=weights, k=1)[0]  # noqa: S311

        # Telegraphed wind-up (#2637 design 2-3): a windup_rounds entry commits
        # to a PendingOpponentAttack instead of a same-round CombatOpponentAction.
        # No CombatOpponentAction row exists for this attack until it matures.
        if chosen.windup_rounds > 0:
            _declare_windup_attack(
                opponent,
                chosen,
                encounter,
                target_pool,
                targeting_participants=targeting_participants,
                rotation=attack_index,
                threat_map=threat_map,
                shield_participant_ids=shield_participant_ids,
            )
            continue

        action = CombatOpponentAction.objects.create(
            opponent=opponent,
            round_number=encounter.round_number,
            threat_entry=chosen,
        )
        _set_npc_action_targets(
            action,
            chosen,
            target_pool,
            targeting_participants=targeting_participants,
            rotation=attack_index,
            threat_map=threat_map,
            shield_participant_ids=shield_participant_ids,
        )
        actions.append(action)

    return actions


def _npc_action_target_pool(
    opponent: CombatOpponent,
    active_participants: list[CombatParticipant],
    encounter: CombatEncounter,
) -> tuple[list, bool]:
    """Route an opponent's targeting by allegiance (#1584 + #1590).

    Two allegiance systems compose here:

    * **#1584 `CombatOpponent.allegiance`** routes an ALLY *summon* onto its
      hostile ENEMY opponents (opponent-vs-opponent damage). Intangible opponents
      (objectdb set, grants_intangibility active) are excluded (#1584 Task 8);
      opponents with no objectdb are kept (they cannot be queried for it).
    * **#1590 threat-read** (`_get_opponent_targets`) refines an ENEMY opponent's
      PC targets — calm (NEUTRAL) yields no PCs (the empty-pool guard then makes it
      skip the round), charm (ALLY_OF_CASTER) excludes the charmer's party.

    An ENEMY opponent targets the (threat-read-filtered) PC side; an ALLY summon
    targets ENEMY opponents. ``active_participants`` is already intangibility- and
    can_act-filtered by ``select_npc_actions``.

    Returns ``(target_pool, targeting_participants)``.
    """
    if opponent.allegiance == CombatAllegiance.ALLY:
        from world.conditions.services import is_untargetable  # noqa: PLC0415

        opponent_pool = [
            opp
            for opp in combatants_hostile_to(opponent)["opponents"]
            if opp.objectdb_id is None or not is_untargetable(opp.objectdb)
        ]
        return opponent_pool, False

    # ENEMY opponent: #1590's allegiance threat-read decides the PC pool.
    return _get_opponent_targets(opponent, active_participants, encounter), True


def _set_npc_action_targets(  # noqa: PLR0913
    action: CombatOpponentAction,
    entry: ThreatPoolEntry,
    target_pool: list,
    *,
    targeting_participants: bool,
    rotation: int,
    threat_map: dict[int, int] | None = None,
    shield_participant_ids: set[int] | None = None,
) -> None:
    """Populate exactly one target relation on an NPC action (#1584)."""
    if targeting_participants:
        action.targets.set(
            _select_targets(
                entry,
                target_pool,
                rotation=rotation,
                _threat_map=threat_map,
                _shield_participant_ids=shield_participant_ids,
            )
        )
    else:
        action.opponent_targets.set(
            _select_opponent_targets(
                entry,
                target_pool,
                rotation=rotation,
                _threat_map=threat_map,
                _shield_participant_ids=shield_participant_ids,
            )
        )


def _select_windup_targets(  # noqa: PLR0913
    entry: ThreatPoolEntry,
    target_pool: list,
    *,
    targeting_participants: bool,
    rotation: int,
    threat_map: dict[int, int] | None = None,
    shield_participant_ids: set[int] | None = None,
) -> list:
    """Same selection ``_set_npc_action_targets`` uses, minus the M2M write (#2637).

    A wind-up has no CombatOpponentAction row to attach an M2M to at
    declaration time — ``PendingOpponentAttack.target`` is a single nullable
    FK instead (v1 single-target). The caller collapses a one-element,
    participant-targeting selection into that FK; anything else (multi/ALL,
    or an opponent-targeting summon windup) stays room-targeting (``None``),
    re-derived at maturation.
    """
    if targeting_participants:
        return _select_targets(
            entry,
            target_pool,
            rotation=rotation,
            _threat_map=threat_map,
            _shield_participant_ids=shield_participant_ids,
        )
    return _select_opponent_targets(
        entry,
        target_pool,
        rotation=rotation,
        _threat_map=threat_map,
        _shield_participant_ids=shield_participant_ids,
    )


# =============================================================================
# Telegraphed enemy wind-ups (#2637)
# =============================================================================


def _declare_windup_attack(  # noqa: PLR0913
    opponent: CombatOpponent,
    entry: ThreatPoolEntry,
    encounter: CombatEncounter,
    target_pool: list,
    *,
    targeting_participants: bool,
    rotation: int,
    threat_map: dict[int, int] | None = None,
    shield_participant_ids: set[int] | None = None,
) -> None:
    """Select this wind-up's target(s) and create its PendingOpponentAttack.

    Split out of ``_build_opponent_round_actions`` to keep that function's
    branch count within the lint threshold (#2637).
    """
    selected = _select_windup_targets(
        entry,
        target_pool,
        targeting_participants=targeting_participants,
        rotation=rotation,
        threat_map=threat_map,
        shield_participant_ids=shield_participant_ids,
    )
    single_target = selected[0] if targeting_participants and len(selected) == 1 else None
    _create_pending_opponent_attack(opponent, entry, encounter, single_target)


def _dual_dispatch_combat_narration(encounter: CombatEncounter, narration: str) -> None:
    """Broadcast a combat narration line to BOTH clients (HARD telnet parity).

    Mirrors ``world.covenants.perks.services.announce_fired_perks``'s
    dual-dispatch shape: a persisted, Narrator-authored OUTCOME Interaction
    over the WS interaction payload
    (``world.combat.interaction_services.broadcast_action_outcome``) PLUS a
    direct ``room.msg_contents(narration)`` text companion so bare telnet
    clients render the identical line — ``broadcast_action_outcome`` alone is
    WS-only.
    """
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    broadcast_action_outcome(encounter=encounter, narration=narration)
    room = encounter.room
    if room is not None:
        room.msg_contents(narration)


def _find_windup_caller(encounter: CombatEncounter) -> CombatParticipant | None:
    """First ACTIVE participant flagged to auto-call enemy wind-ups (#2637 design 6).

    A participant qualifies when their character holds an active
    (``left_at__isnull=True``), engaged ``CharacterCovenantRole`` whose
    ``covenant_role`` (or that role's ``parent_role`` — the riding rule
    mirrors ``CovenantRole.blend_weight_for``) has ``calls_out_windups=True``.
    Deterministic by participant pk. Two queries total (participants, then one
    batched membership query), never a query per candidate.
    """
    from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415

    participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        .select_related("character_sheet__character")
        .order_by("pk")
    )
    if not participants:
        return None

    sheet_ids = [p.character_sheet_id for p in participants]
    flagged_sheet_ids = set(
        CharacterCovenantRole.objects.filter(
            character_sheet_id__in=sheet_ids,
            engaged=True,
            left_at__isnull=True,
        )
        .filter(
            Q(covenant_role__calls_out_windups=True)
            | Q(covenant_role__parent_role__calls_out_windups=True)
        )
        .values_list("character_sheet_id", flat=True)
    )
    for participant in participants:
        if participant.character_sheet_id in flagged_sheet_ids:
            return participant
    return None


def _broadcast_windup_telegraph(pending: PendingOpponentAttack, *, caller_name: str | None) -> None:
    """Announce a newly-declared wind-up (#2637 design 2, 6)."""
    template = pending.threat_entry.windup_telegraph or WINDUP_GENERIC_TELEGRAPH
    narration = template.format(opponent=pending.opponent.name)
    if caller_name:
        narration = f"{narration} — {caller_name} calls it!"
    _dual_dispatch_combat_narration(pending.encounter, narration)


def _broadcast_windup_wreck(pending: PendingOpponentAttack, attacker_name: str) -> None:
    """Announce a PC hit staggering a winding-up opponent (#2637 design 4)."""
    narration = f"{attacker_name}'s strike staggers {pending.opponent.name}'s wind-up!"
    _dual_dispatch_combat_narration(pending.encounter, narration)


def _broadcast_windup_fizzled(pending: PendingOpponentAttack, *, reason: str = "") -> None:
    """Announce a wind-up that never lands (#2637 design 3)."""
    if reason:
        narration = f"{pending.opponent.name}'s wind-up {reason} and comes to nothing!"
    else:
        narration = (
            f"{pending.opponent.name}'s wind-up is broken entirely — the perfect chain cancels it!"
        )
    _dual_dispatch_combat_narration(pending.encounter, narration)


def _create_pending_opponent_attack(
    opponent: CombatOpponent,
    entry: ThreatPoolEntry,
    encounter: CombatEncounter,
    target: CombatParticipant | None,
) -> PendingOpponentAttack:
    """Telegraph a wind-up instead of a same-round attack (#2637 design 2-3, 6).

    Resolves auto-callout (at most one call-out per round per encounter) and
    dual-dispatches the telegraph narration.
    """
    round_number = encounter.round_number
    already_called_out = PendingOpponentAttack.objects.filter(
        encounter=encounter,
        declared_round=round_number,
        called_out=True,
    ).exists()
    caller = None if already_called_out else _find_windup_caller(encounter)

    pending = PendingOpponentAttack.objects.create(
        encounter=encounter,
        opponent=opponent,
        threat_entry=entry,
        target=target,
        declared_round=round_number,
        resolves_round=round_number + entry.windup_rounds,
        called_out=caller is not None,
    )
    caller_name = str(caller.character_sheet.character) if caller is not None else None
    _broadcast_windup_telegraph(pending, caller_name=caller_name)
    return pending


def _windup_damage_scale(downgrades: int) -> float:
    """The downgrade ladder: x(1 - 0.25*downgrades), floored at x0.25 (#2637 design 3)."""
    return max(WINDUP_MIN_DAMAGE_SCALE, 1.0 - WINDUP_DOWNGRADE_STEP * downgrades)


def _mature_one_pending_attack(
    encounter: CombatEncounter,
    pending: PendingOpponentAttack,
    round_number: int,
) -> None:
    """Resolve a single matured wind-up: fizzle, lose-target, or fire (#2637 design 3)."""
    from world.vitals.services import is_dead  # noqa: PLC0415

    if pending.downgrades >= WINDUP_FIZZLE_DOWNGRADES:
        _broadcast_windup_fizzled(pending)
        pending.delete()
        return

    if pending.opponent.status != OpponentStatus.ACTIVE:
        pending.delete()
        return

    entry = pending.threat_entry
    scale = _windup_damage_scale(pending.downgrades)

    if pending.target_id is not None:
        target = pending.target
        if target.status != ParticipantStatus.ACTIVE or is_dead(target.character_sheet):
            _broadcast_windup_fizzled(pending, reason="loses its target")
            pending.delete()
            return
        action = CombatOpponentAction.objects.create(
            opponent=pending.opponent,
            round_number=round_number,
            threat_entry=entry,
            damage_scale=scale,
            matured_from_called_out_windup=pending.called_out,
        )
        action.targets.set([target])
        pending.delete()
        return

    # Room-targeting wind-up (no single stored target): re-derive the pool at
    # maturation the same way declaration did — participants may have fled,
    # died, or joined since the wind-up was telegraphed.
    active_participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        ).select_related("character_sheet__character")
    )
    target_pool, targeting_participants = _npc_action_target_pool(
        pending.opponent, active_participants, encounter
    )
    if not target_pool:
        _broadcast_windup_fizzled(pending, reason="loses its target")
        pending.delete()
        return

    action = CombatOpponentAction.objects.create(
        opponent=pending.opponent,
        round_number=round_number,
        threat_entry=entry,
        damage_scale=scale,
        matured_from_called_out_windup=pending.called_out,
    )
    _set_npc_action_targets(
        action,
        entry,
        target_pool,
        targeting_participants=targeting_participants,
        rotation=0,
    )
    pending.delete()


def _mature_pending_opponent_attacks(encounter: CombatEncounter, round_number: int) -> None:
    """Mature every wind-up whose delay has elapsed this round (#2637 design 3, 5).

    Called from ``resolve_round`` after the encounter flips to RESOLVING but
    BEFORE the round's ``CombatOpponentAction`` rows are queried, so a matured
    wind-up's synthesized action is picked up by the normal NPC-resolution
    pipeline unmodified in the same pass.
    """
    pending_rows = list(
        PendingOpponentAttack.objects.filter(
            encounter=encounter,
            resolves_round=round_number,
        ).select_related("opponent", "threat_entry", "target__character_sheet__character")
    )
    for pending in pending_rows:
        _mature_one_pending_attack(encounter, pending, round_number)


def _apply_windup_interception_rider(
    target: CombatOpponent,
    outcome: ActionOutcome,
    attacker_participant: CombatParticipant,
) -> None:
    """A landing PC hit on a winding-up opponent adds downgrades (#2637 design 4).

    Only fires on hits that dealt damage > 0 against ``target``. +1 downgrade
    blind, +2 when the wind-up is ``called_out`` (called-out beats blind).
    Only matches a NOT-YET-MATURED pending row (``resolves_round >=`` the
    current round) — a wind-up maturing THIS round is already resolved and
    deleted before PC actions resolve, so this can only ever reach a future
    one.
    """
    landed = any(
        isinstance(damage_result, OpponentDamageResult)
        and damage_result.opponent_id == target.pk
        and damage_result.damage_dealt > 0
        for damage_result in outcome.damage_results
    )
    if not landed:
        return

    pending = PendingOpponentAttack.objects.filter(
        opponent=target,
        resolves_round__gte=target.encounter.round_number,
    ).first()
    if pending is None:
        return

    increment = WINDUP_CALLED_OUT_DOWNGRADE if pending.called_out else WINDUP_BLIND_DOWNGRADE
    pending.downgrades += increment
    pending.save(update_fields=["downgrades"])
    _broadcast_windup_wreck(pending, str(attacker_participant.character_sheet.character))


# ---------------------------------------------------------------------------
# Sent Flying (#2638) — the plummet-pattern's first "in-flight" consequence.
#
# A sends_flying ThreatPoolEntry's attack that lands damage > 0 applies the
# seeded "Sent Flying" marker condition (a produced, reactable moment — see
# world.combat.sent_flying_content) and is IMMEDIATELY answerable by the same
# armed-INTERPOSE reaction economy _try_interpose reads. Left unanswered, the
# marker resolves explicitly at the end of resolve_round: a plummet if the
# victim's room supports one, else a hard-landing impact debit.
# ---------------------------------------------------------------------------


def _broadcast_sent_flying_launch(participant: CombatParticipant) -> None:
    """Announce a Sent Flying marker landing (#2638) — the produced moment."""
    name = str(participant.character_sheet.character)
    narration = f"{name} is sent FLYING by the blow!"
    _dual_dispatch_combat_narration(participant.encounter, narration)


def _sent_flying_windup_caller(
    encounter: CombatEncounter, npc_action: CombatOpponentAction
) -> str | None:
    """The wind-up caller's name if *npc_action* matured from a called-out wind-up.

    ``PendingOpponentAttack`` (which carries ``called_out``) is deleted at
    maturation, so ``matured_from_called_out_windup`` is the only surviving
    record. v1 approximation: re-derives the CURRENT flagged auto-caller via
    ``_find_windup_caller`` rather than persisting the specific caller who
    called THIS wind-up out — at most one call-out fires per round per
    encounter (#2637 design 6), so this is accurate whenever the flagged role
    hasn't changed hands mid-round, which is the overwhelmingly common case.
    """
    if not npc_action.matured_from_called_out_windup:
        return None
    caller = _find_windup_caller(encounter)
    return str(caller.character_sheet.character) if caller is not None else None


def _broadcast_sent_flying_catch(
    participant: CombatParticipant,
    npc_action: CombatOpponentAction,
    catcher: ObjectDB,  # noqa: OBJECTDB_PARAM
) -> None:
    """Announce a mid-air catch (#2638), naming the catcher + the caller if any."""
    victim_name = str(participant.character_sheet.character)
    narration = f"{catcher} catches {victim_name} out of the air!"
    caller_name = _sent_flying_windup_caller(participant.encounter, npc_action)
    if caller_name:
        narration = f"{narration} {caller_name}'s call-out made the difference!"
    _dual_dispatch_combat_narration(participant.encounter, narration)


def _try_catch_sent_flying(participant: CombatParticipant) -> Character | None:
    """Find and fire the first eligible armed INTERPOSE to catch a Sent Flying victim.

    Same query shape as :func:`_try_interpose` (an armed INTERPOSE this round
    whose ``focused_ally_target`` is *participant* or ``None``), restricted to
    ACTIVE participants and excluding self-interpose. The fire gate is
    budget-only — ``REACTIONS_PER_ROUND`` via the interposer's
    ``reactions_used`` (#2639) — and deliberately never calls
    ``dispatch_interpose``/the mundane or technique challenge chain: that
    machinery grades HOW MUCH of a landing hit's *amount* a block reduces,
    which has no meaning for a mid-air catch (a binary rescue, not gradeable
    damage mitigation). "Fires" here means the SAME thing
    ``_dispatch_interpose_action``'s docstring documents for the mundane path:
    an attempt that clears budget, independent of any roll. Only one guardian
    is ever queried (the first eligible), so
    ``combat.constants.ABSORPTION_CAP_PER_MOMENT`` — built for multiple
    interceptors answering ONE ``DamagePreApplyPayload`` — has no second
    attempt to cap here; not consulted (documented v1 scope, #2638).

    Returns the catching Character on fire, or None (no eligible/budget-
    exhausted guardian — the marker stays for explicit resolution).
    """
    encounter = participant.encounter
    if encounter.status != RoundStatus.RESOLVING:
        return None

    # Q(...) | Q(...), not `focused_ally_target__in=[participant, None]`: the
    # latter silently drops the None entry (Django compiles field__in with a
    # None member to a bare `IN (x)`, never `x OR field IS NULL`) — see the
    # bug-fix note on _try_interpose's identical query, discovered while
    # writing this sibling (#2638).
    action = (
        CombatRoundAction.objects.filter(
            Q(focused_ally_target=participant) | Q(focused_ally_target__isnull=True),
            participant__encounter=encounter,
            round_number=encounter.round_number,
            maneuver=CombatManeuver.INTERPOSE,
            participant__status=ParticipantStatus.ACTIVE,
        )
        .exclude(participant=participant)
        .select_related("participant__character_sheet__character")
        .first()
    )
    if action is None:
        return None

    interposer = action.participant
    if interposer.reactions_used >= REACTIONS_PER_ROUND:
        return None

    interposer.reactions_used += 1
    interposer.save(update_fields=["reactions_used"])
    return interposer.character_sheet.character


def _clear_sent_flying_marker(
    participant: CombatParticipant,
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
    template: ConditionTemplate,
) -> None:
    """Remove the Sent Flying condition + reset its damage carrier (#2638)."""
    from world.conditions.services import remove_condition  # noqa: PLC0415

    remove_condition(character, template)
    participant.sent_flying_damage = 0
    participant.save(update_fields=["sent_flying_damage"])


def _trigger_sent_flying(
    participant: CombatParticipant,
    npc_action: CombatOpponentAction,
    damage: int,
) -> None:
    """Apply the Sent Flying marker and consult the reaction seam (#2638).

    Fires when a ``sends_flying`` ThreatPoolEntry's attack lands damage > 0 on
    a PC participant (called from ``_resolve_npc_action_on_target``). Applies
    the seeded marker, stamps the triggering damage onto
    ``CombatParticipant.sent_flying_damage`` (the v1 carrier — see that
    field's help text), dual-dispatches the produced-moment narration, then
    IMMEDIATELY consults :func:`_try_catch_sent_flying`. A landed catch clears
    the marker and celebrates; otherwise the marker is left in place, silent,
    for :func:`_resolve_sent_flying_markers` at end of round.
    """
    from world.combat.sent_flying_content import SENT_FLYING_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415

    character = participant.character_sheet.character
    try:
        template = ConditionTemplate.get_by_name(SENT_FLYING_CONDITION_NAME)
    except ConditionTemplate.DoesNotExist:
        # Unseeded content (mirrors _ensure_interpose_challenges' warn-and-skip
        # shape) — a dev/test environment that never ran ensure_sent_flying_content.
        return

    apply_condition(character, template)
    participant.sent_flying_damage = damage
    participant.save(update_fields=["sent_flying_damage"])
    _broadcast_sent_flying_launch(participant)

    catcher = _try_catch_sent_flying(participant)
    if catcher is None:
        return
    _clear_sent_flying_marker(participant, character, template)
    _broadcast_sent_flying_catch(participant, npc_action, catcher)


def _resolve_one_sent_flying_landing(
    participant: CombatParticipant,
    template: ConditionTemplate,
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
) -> None:
    """Land one unanswered Sent Flying marker: plummet chain, or a hard impact (#2638).

    Reuses the plummet system's own fall-eligibility seam
    (``maybe_emit_fall`` — emits ``EventName.FELL`` only when the destination
    Position is CHASM) rather than reimplementing it: if the victim's room has
    a CHASM position, they are launched over the edge into it and
    ``maybe_emit_fall`` hands off to the existing multi-round descent +
    CATCH_THE_FALLER machinery — zero new machinery, per the design.
    Otherwise this is a hard, unassisted landing: a second Physical debit of
    ``floor(sent_flying_damage * SENT_FLYING_IMPACT_FRACTION)`` through the
    STANDARD combat damage path (``apply_damage_to_participant`` +
    ``process_damage_consequences`` — the same two-call shape
    ``_resolve_npc_action_on_target`` uses for every other NPC hit), resolved
    at its full computed value with NO extra narration beyond whatever that
    standard path already produces — the celebrate/silence boundary: an
    unanswered landing is unremarked. The marker + its damage carrier are
    cleared either way.
    """
    from world.areas.positioning.constants import PositionKind  # noqa: PLC0415
    from world.areas.positioning.models import Position  # noqa: PLC0415
    from world.areas.positioning.services import (  # noqa: PLC0415
        force_move_to_position,
        maybe_emit_fall,
    )
    from world.combat.sent_flying_content import (  # noqa: PLC0415
        SENT_FLYING_IMPACT_DAMAGE_TYPE_NAME,
    )
    from world.conditions.models import DamageType  # noqa: PLC0415
    from world.vitals.services import process_damage_consequences  # noqa: PLC0415

    damage = participant.sent_flying_damage
    _clear_sent_flying_marker(participant, character, template)

    room = character.location
    chasm = (
        Position.objects.filter(room=room, kind=PositionKind.CHASM).first()
        if room is not None
        else None
    )
    if chasm is not None:
        force_move_to_position(character, chasm)
        maybe_emit_fall(character, chasm)
        return

    impact = math.floor(damage * SENT_FLYING_IMPACT_FRACTION)
    if impact <= 0:
        return

    damage_type = DamageType.objects.filter(name=SENT_FLYING_IMPACT_DAMAGE_TYPE_NAME).first()
    dmg_result = apply_damage_to_participant(
        participant,
        impact,
        damage_type=damage_type,
    )
    process_damage_consequences(
        character_sheet=participant.character_sheet,
        damage_dealt=dmg_result.damage_dealt,
        damage_type=damage_type,
    )


def _resolve_sent_flying_markers(encounter: CombatEncounter) -> None:
    """Explicitly resolve every unanswered Sent Flying marker at round end (#2638).

    Mirrors the plummet system's own explicit-resolution idiom — never a
    per-round DoT tick. Batches: one participant query (candidates carrying a
    nonzero damage carrier) + one BATCHED ``ConditionInstance`` existence
    check across every candidate's character (never a query per participant —
    "no queries in loops"); a candidate whose marker was already cleared by a
    mid-air catch (or removed by some other path) just gets its stale carrier
    zeroed, no landing resolution. Called from ``resolve_round`` after the
    round-tick pass and before boss phase transitions.
    """
    from world.combat.sent_flying_content import SENT_FLYING_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionInstance, ConditionTemplate  # noqa: PLC0415

    try:
        template = ConditionTemplate.get_by_name(SENT_FLYING_CONDITION_NAME)
    except ConditionTemplate.DoesNotExist:
        return

    marked = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
            sent_flying_damage__gt=0,
        ).select_related("character_sheet__character")
    )
    if not marked:
        return

    character_ids = [p.character_sheet.character_id for p in marked]
    still_marked_ids = set(
        ConditionInstance.objects.filter(
            condition=template,
            target_id__in=character_ids,
            is_suppressed=False,
        ).values_list("target_id", flat=True)
    )

    for p in marked:
        character = p.character_sheet.character
        if character.id not in still_marked_ids:
            # Stale carrier (marker already cleared elsewhere) — just reset it.
            p.sent_flying_damage = 0
            p.save(update_fields=["sent_flying_damage"])
            continue
        _resolve_one_sent_flying_landing(p, template, character)


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


def _zero_opponent_damage_result(opponent: CombatOpponent) -> OpponentDamageResult:
    """A no-effect damage result (hit cancelled or reduced to nothing)."""
    return OpponentDamageResult(
        damage_dealt=0,
        health_damaged=False,
        probed=False,
        probing_increment=0,
        defeated=False,
        kills=0,
        opponent_id=opponent.pk,
    )


def _apply_swarm_damage(opponent: CombatOpponent, raw_damage: int) -> OpponentDamageResult:
    """Resolve a landing hit on a SWARM opponent (#875).

    Swarms have no HP, soak, or probing — a landing attack clears bodies.
    """
    kills = min(swarm_kills(raw_damage, opponent.body_toughness or 1), opponent.swarm_count)
    opponent.swarm_count -= kills
    defeated = opponent.swarm_count <= 0
    if defeated:
        opponent.status = OpponentStatus.DEFEATED
    opponent.save(update_fields=["swarm_count", "status"])
    return OpponentDamageResult(
        damage_dealt=kills,
        health_damaged=False,
        probed=False,
        probing_increment=0,
        defeated=defeated,
        kills=kills,
        opponent_id=opponent.pk,
    )


def _emit_opponent_pre_apply(
    opponent: CombatOpponent,
    raw_damage: int,
    damage_type: DamageType | None,
    source_sheet: CharacterSheet | None,
) -> tuple[int, bool]:
    """Emit DAMAGE_PRE_APPLY for an opponent; return ``(amount, dropped)``.

    Mirrors the participant path so reactive defences (force-field/reflect/blink)
    fire on NPCs and ALLY summons identically (#1584). Returns the possibly
    mutated damage amount and whether the hit should be dropped — the event
    cancelled it, or the mutated amount fell to <= 0. Opponents with no
    objectdb/location skip the event (amount unchanged, never dropped here).
    """
    if opponent.objectdb is None or opponent.objectdb.location is None:
        return raw_damage, False
    damage_source = classify_source(source_sheet.character if source_sheet is not None else None)
    pre_payload = DamagePreApplyPayload(
        target=opponent.objectdb,
        amount=raw_damage,
        damage_type=damage_type,
        source=damage_source,
    )
    stack = emit_event(
        EventName.DAMAGE_PRE_APPLY,
        pre_payload,
        location=opponent.objectdb.location,
    )
    if stack.was_cancelled():
        return raw_damage, True
    return pre_payload.amount, pre_payload.amount <= 0


def _try_guardian_shield_opponent(
    opponent: CombatOpponent,
    raw_damage: int,
    damage_type: DamageType | None,
    source_sheet: CharacterSheet | None,
) -> tuple[int, bool]:
    """Guardian-shields-a-summon (#2207): run ANY-ALLY Interpose for an
    ALLY-allegiance ``CombatOpponent`` ward. Return ``(amount, dropped)``,
    mirroring :func:`_emit_opponent_pre_apply`'s contract — ``dropped=True``
    means the guardian fully blocked the hit and the caller should return a
    zero damage result.

    No-op passthrough (amount unchanged, never dropped) when *opponent* is not
    ``allegiance=ALLY`` (an ENEMY opponent is never a ward) or has no
    ``objectdb`` (nothing to bind the interpose challenge/ward target to).
    """
    if opponent.allegiance != CombatAllegiance.ALLY or opponent.objectdb is None:
        return raw_damage, False

    interpose_source = classify_source(source_sheet.character if source_sheet is not None else None)
    interpose_payload = DamagePreApplyPayload(
        target=opponent.objectdb,
        amount=raw_damage,
        damage_type=damage_type,
        source=interpose_source,
    )
    _try_interpose_for_opponent(opponent, interpose_payload)
    amount = int(interpose_payload.amount)
    return amount, amount <= 0


def _resolve_opponent_pre_apply(
    opponent: CombatOpponent,
    raw_damage: int,
    damage_type: DamageType | None,
    source_sheet: CharacterSheet | None,
    *,
    skip_guardian_shield: bool = False,
) -> tuple[int, bool]:
    """Run DAMAGE_PRE_APPLY, then guardian-shields-a-summon (#2207), for an opponent.

    Combines :func:`_emit_opponent_pre_apply` and
    :func:`_try_guardian_shield_opponent` into a single ``(amount, dropped)``
    step for :func:`apply_damage_to_opponent` — the guardian check only runs
    when the reactive DAMAGE_PRE_APPLY step didn't already drop the hit, so a
    cancelled/zeroed hit never charges the guardian's interpose fatigue for
    blocking a hit that no longer exists (mirrors
    :func:`apply_damage_to_participant`'s ordering).

    ``skip_guardian_shield=True`` skips ONLY :func:`_try_guardian_shield_opponent`
    — :func:`_emit_opponent_pre_apply` (the opponent's own DAMAGE_PRE_APPLY
    trigger band) still runs. Used by :func:`_try_companion_defend`'s redirect
    to avoid double-charging a guardian that already had a chance to interpose
    earlier in the same blow.

    Rampart interception (#2209) runs first, before the DAMAGE_PRE_APPLY emit —
    an opponent (e.g. an ALLY summon) standing at a rampart-covered position is
    shielded exactly like a PC. No threat entry is available on this path, so
    delivery/is_area default to MELEE/False.
    """
    if opponent.objectdb is not None:
        raw_damage = apply_rampart_interception(
            opponent.objectdb,
            raw_damage,
            damage_type,
            attacker_ref=source_sheet.character if source_sheet is not None else None,
        )
    raw_damage, dropped = _emit_opponent_pre_apply(opponent, raw_damage, damage_type, source_sheet)
    if dropped:
        return raw_damage, True
    if skip_guardian_shield:
        return raw_damage, False
    return _try_guardian_shield_opponent(opponent, raw_damage, damage_type, source_sheet)


def _resolve_opponent_defeat(opponent: CombatOpponent, source_sheet: CharacterSheet | None) -> bool:
    """Resolve whether an opponent at 0 HP is actually defeated.

    Story-criticality check: prevent death if the NPC is load-bearing for a
    story the attacker isn't part of (#1874). When death is prevented, the
    NPC flees instead and ``False`` is returned. Otherwise the opponent's
    status is set to DEFEATED and ``True`` is returned.
    """
    from world.stories.flee_services import flee_story_critical_npc  # noqa: PLC0415
    from world.stories.npc_protection import (  # noqa: PLC0415
        is_death_prevented_by_story,
    )

    npc_sheet = None
    if opponent.objectdb is not None:
        try:
            npc_sheet = opponent.objectdb.sheet_data
        except AttributeError:
            npc_sheet = None
    attacker = source_sheet.character if source_sheet else None
    if npc_sheet is not None and is_death_prevented_by_story(npc_sheet, attacker):
        flee_story_critical_npc(opponent, attacker)
        return False
    opponent.status = OpponentStatus.DEFEATED
    return True


def _is_vulnerable(opponent: CombatOpponent) -> bool:
    """Return True if the opponent's break-bar vulnerability window is active."""
    return opponent.vulnerability_rounds_remaining > 0


def _effective_soak_for_opponent(opponent: CombatOpponent, bypass_soak: bool) -> int:
    """Return the effective soak value, bypassed by bypass_soak or vulnerability."""
    if bypass_soak or _is_vulnerable(opponent):
        return 0
    return opponent.soak_value


def _effective_resistance_for_opponent(
    opponent: CombatOpponent, damage_type: DamageType | None
) -> int:
    """Return damage-type resistance, bypassed during vulnerability window."""
    if damage_type is None or opponent.objectdb is None or _is_vulnerable(opponent):
        return 0
    return opponent.objectdb.conditions.resistance_modifier(damage_type)


def _apply_condition_damage_interactions(
    target: ObjectDB,  # noqa: OBJECTDB_PARAM
    damage_type: DamageType | None,
    damage_amount: int,
) -> tuple[int, DamageInteractionResult | None]:
    """Run condition-damage interactions on a target, returning modified damage + result.

    Called from both combat damage paths after soak/resistance/armor (#2018).
    The interaction modifier is a final percentage multiplier on net damage — SUMMED
    across every matching ``ConditionDamageInteraction`` row, then clamped to
    ``±ENEMY_LANE_CAP_PERCENT`` (#2643, Undermine's enemy-side lane; the same EQ2 lane
    guard as the team-damage-percent lane — see ``world.magic.constants
    .TEAM_BUFF_LANE_CAP_PERCENT``). The clamp applies to the summed percent, not to any
    individual authored row — an authored row may itself exceed the band; only the
    live total a target can accumulate is bounded.
    Returns ``(modified_damage, interaction_result)`` — ``interaction_result``
    is None when damage_type is None, a non-model value, or damage_amount is zero.
    """
    if damage_type is None or damage_amount <= 0:
        return damage_amount, None
    # Some callers pass a string damage_type (e.g. "physical") rather than a
    # DamageType model instance. Condition-damage interactions require a real
    # model to query the interaction table — skip for non-model values.
    from world.conditions.models import DamageType  # noqa: PLC0415

    if not isinstance(damage_type, DamageType):
        return damage_amount, None
    from world.conditions.services import process_damage_interactions  # noqa: PLC0415

    result = process_damage_interactions(target, damage_type)
    if result.damage_modifier_percent != 0:
        clamped_percent = max(
            -ENEMY_LANE_CAP_PERCENT, min(ENEMY_LANE_CAP_PERCENT, result.damage_modifier_percent)
        )
        damage_amount = max(0, int(damage_amount * (1 + clamped_percent / 100)))
    return damage_amount, result


def _opponent_health_before_pct(opponent: CombatOpponent) -> float:
    """Pre-hit health fraction for an opponent (#2643 execute basis). 0.0 when maxless."""
    if opponent.max_health <= 0:
        return 0.0
    return max(0.0, opponent.health / opponent.max_health)


def _apply_execute_multiplier(
    damage_amount: int, multiplier: Decimal, health_before_pct: float
) -> int:
    """Scale damage up as the target's PRE-hit health runs low (#2643 execute).

    ``factor = 1 + multiplier * missing_health_fraction`` where
    ``missing_health_fraction = 1 - health_before_pct``. A zero (the default on every
    damage profile) or falsy ``multiplier`` is a byte-identical no-op — every existing
    damage test is unaffected. Basis is always PRE-hit health (captured by the caller
    before this hit's own subtraction), so a second hit in the same exchange correctly
    prices off the health the FIRST hit left behind — never a recursive
    self-referential fraction, no matter how many hits land in sequence.
    """
    if not multiplier:
        return damage_amount
    missing_health_fraction = 1.0 - health_before_pct
    factor = 1 + float(multiplier) * missing_health_fraction
    return max(0, int(damage_amount * factor))


def apply_damage_to_opponent(  # noqa: PLR0913
    opponent: CombatOpponent,
    raw_damage: int,
    *,
    bypass_soak: bool = False,
    bypass_pre_apply: bool = False,
    damage_type: DamageType | None = None,
    source_sheet: CharacterSheet | None = None,
    skip_guardian_shield: bool = False,
    execute_missing_health_multiplier: Decimal = Decimal(0),
) -> OpponentDamageResult:
    """Apply damage to an NPC opponent, accounting for soak, probing,
    and damage-type resistance.

    All raw damage (even fully soaked) contributes to probing. Only damage
    that exceeds soak and resistance actually reduces health.

    When ``source_sheet`` is provided, increments the source's achievement
    counters: ``damage_dealt`` (by post-soak damage), and on defeat
    ``opponents_defeated``.

    ``skip_guardian_shield=True`` skips ONLY the guardian-shields-a-summon
    (#2207) hook — the opponent's own DAMAGE_PRE_APPLY trigger band still
    runs. See :func:`_resolve_opponent_pre_apply`.

    ``execute_missing_health_multiplier`` (#2643): the resolving technique damage
    profile's ``execute_missing_health_multiplier`` (default 0 = no-op, matching every
    existing caller byte-for-byte). Scales damage up as the opponent's PRE-hit health
    runs low — see :func:`_apply_execute_multiplier`. The caller (a technique's damage
    resolution — ``CombatTechniqueResolver._apply_profiles_to_target``) is the one place
    the damage profile is in hand; everywhere else defaults to inert.
    """
    # Swarm: no HP, no soak, no probing -- a landing attack clears bodies.
    if opponent.tier == OpponentTier.SWARM and opponent.swarm_count is not None:
        del source_sheet
        return _apply_swarm_damage(opponent, raw_damage)

    # DAMAGE_PRE_APPLY (cancellable, amount mutable). bypass_pre_apply=True skips
    # emit + mutation; the bounced-reflect path uses this to terminate re-emission
    # (loop guard).
    if not bypass_pre_apply:
        # DAMAGE_PRE_APPLY, then guardian-shields-a-summon (#2207) for
        # ALLY-allegiance opponents — see _resolve_opponent_pre_apply.
        raw_damage, dropped = _resolve_opponent_pre_apply(
            opponent,
            raw_damage,
            damage_type,
            source_sheet,
            skip_guardian_shield=skip_guardian_shield,
        )
        if dropped:
            return _zero_opponent_damage_result(opponent)

    effective_soak = _effective_soak_for_opponent(opponent, bypass_soak)

    resistance = _effective_resistance_for_opponent(opponent, damage_type)

    damage_through = max(0, raw_damage - effective_soak - resistance)

    # Execute (#2643): smooth ramp off the opponent's PRE-hit health, captured here
    # before this hit's own subtraction below — a second profile/hit in the same cast
    # (AoE, multi-profile techniques) correctly compounds off each opponent's own
    # already-reduced health, never a recursive fraction. Placed right before the
    # condition-damage-interaction multiply per design (both are final-stage percent
    # scalers on net damage; order between them doesn't change per-technique intent
    # since only one technique's profile ever supplies a nonzero multiplier per hit).
    damage_through = _apply_execute_multiplier(
        damage_through,
        execute_missing_health_multiplier,
        _opponent_health_before_pct(opponent),
    )

    # Condition-damage interactions (#2018). Final percentage multiplier on
    # net damage, after soak + resistance. May consume/transform conditions.
    interaction_result = None
    if damage_through > 0 and opponent.objectdb is not None:
        damage_through, interaction_result = _apply_condition_damage_interactions(
            opponent.objectdb, damage_type, damage_through
        )

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
        defeated = _resolve_opponent_defeat(opponent, source_sheet)

    # Break active engagement lock on opponent defeat (#2020).
    if defeated:
        from world.combat.constants import LockBreakReason  # noqa: PLC0415
        from world.combat.engagement_locks import break_engagement_lock  # noqa: PLC0415

        active_lock = EngagementLock.objects.filter(
            opponent=opponent,
            status=EngagementLockStatus.ACTIVE,
        ).first()
        if active_lock is not None:
            break_engagement_lock(active_lock, reason=LockBreakReason.DEFEAT)

    opponent.save(update_fields=["health", "probing_current", "status"])

    # Achievement counters: see world.combat.achievement_counters. Wired in
    # a follow-up phase — keeping the source_sheet kwarg in place so the
    # call sites are pre-threaded.
    # Threat accumulation: damage dealt -> ThreatRecord increment (#2020).
    # Only post-soak, post-resistance damage (damage_through) contributes — the
    # real signal of who is hurting the NPC. No source_sheet = no threat record.
    if source_sheet is not None and damage_through > 0:
        participant = CombatParticipant.objects.filter(
            encounter=opponent.encounter,
            character_sheet=source_sheet,
        ).first()
        if participant is not None:
            accumulate_threat(opponent.encounter, opponent, participant, damage_through)
    del source_sheet

    return OpponentDamageResult(
        damage_dealt=damage_through,
        health_damaged=damage_through > 0,
        probed=probing_increment > 0,
        probing_increment=probing_increment,
        defeated=defeated,
        kills=0,
        opponent_id=opponent.pk,
        damage_interaction=interaction_result,
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
    - ``ENEMY`` → every ACTIVE ``allegiance=ENEMY`` opponent's ``objectdb``. An
      ALLY summon fights on the actor's side, so enemy-targeted AoE never lands on
      it (#1584). Mirrors ``_resolve_condition_target``'s ENEMY branch, which
      returns ``opp.objectdb`` for an active opponent. Every opponent (including
      ephemeral CombatNPCs) is created with an ObjectDB by ``add_opponent``; the FK
      is only nulled if the ObjectDB is destroyed externally, so we skip opponents
      whose ``objectdb`` is None — matching the focused path's None-guard.
    - ``ALLY`` → every ACTIVE participant except the actor.

    When ``technique.combo_opening_probing`` is set, every ACTIVE ENEMY opponent
    gains that much probing (the combo-opening reward) via ``increment_probing`` —
    the combo-opening effect for ephemeral opponents regardless of conditions.
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

    # Combo-opening probing: granted to every active ENEMY opponent independent of
    # any condition application (the combo-opening effect for ephemeral opponents).
    # ALLY summons are on the actor's side, so probing them is meaningless (#1584).
    if technique.combo_opening_probing:
        for opp in active_opponents:
            if opp.allegiance == CombatAllegiance.ENEMY:
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
            targets = [
                opp.objectdb
                for opp in active_opponents
                if opp.allegiance == CombatAllegiance.ENEMY and opp.objectdb is not None
            ]
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


def _refresh_participant_trigger_handlers(encounter: CombatEncounter) -> None:
    """Make passive-installed reactive triggers visible within the same round.

    ``_resolve_passive_actions`` may install reactive conditions (e.g. DEFEND's
    Shielded) on allies. Installing a reactive condition creates ``Trigger`` rows
    and calls ``TriggerHandler.on_trigger_added`` → ``invalidate``, which defers the
    cache reset to ``transaction.on_commit``. But ``resolve_round`` runs the whole
    round inside one ``@transaction.atomic`` block, so that ``on_commit`` callback
    does not fire until *after* this round's damage resolution — meaning the new
    triggers would be invisible to the very NPC attack they are meant to mitigate.

    Synchronously refresh each active participant's character trigger handler so the
    freshly ``bulk_create``d rows (already visible in this transaction) are loaded
    before ``_resolve_actions`` runs. The deferred ``on_commit(_reset)`` remains
    intact as the cross-transaction/rollback safety net.
    """
    participants = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).select_related("character_sheet__character")
    for participant in participants:
        character = participant.character_sheet.character
        handler = character.trigger_handler
        if handler is not None:
            handler.refresh()


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


def _emit_post_damage_events(  # noqa: PLR0913
    *,
    character: Character,
    room: ObjectDB | None,
    effective_damage: int,
    damage_type: DamageType | None,
    damage_source: DamageSource,
    health_after: int,
    knockout_eligible: bool,
    was_in_knockout_band: bool,
    death_eligible: bool,
    force_death: bool,
) -> None:
    """Emit DAMAGE_APPLIED, CHARACTER_INCAPACITATED, and CHARACTER_KILLED events post-save.

    Called after vitals.save(); no-op when room is None (unlocated characters).
    """
    if room is None:
        return
    applied_payload = DamageAppliedPayload(
        target=character,
        amount_dealt=effective_damage,
        damage_type=damage_type,
        source=damage_source,
        hp_after=health_after,
    )
    emit_event(EventName.DAMAGE_APPLIED, applied_payload, location=room)

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


def _run_pre_apply_interceptors(
    participant: CombatParticipant,
    pre_payload: DamagePreApplyPayload,
    room: ObjectDB | None,
    vitals: CharacterVitals,
) -> ParticipantDamageResult | None:
    """Run the cancellable ``DAMAGE_PRE_APPLY`` event and reactive interceptors.

    Returns a zero-damage ``ParticipantDamageResult`` when the event is
    cancelled or the amount is fully zeroed by a reactive interceptor
    (blink/reflect/force-field) — signalling an early exit. Returns ``None``
    when the payload survives and interception (interpose/companion-defend)
    has been applied.
    """
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

    # A reactive interceptor (blink/reflect/force-field) that fully avoids the
    # hit zeroes pre_payload.amount via mutation rather than CANCEL_EVENT (#1584).
    # Short-circuit BEFORE _try_interpose so an ally is not charged interpose
    # fatigue for blocking a hit that no longer exists.
    if pre_payload.amount <= 0:
        return ParticipantDamageResult(
            damage_dealt=0,
            health_after=vitals.health,
            knockout_eligible=False,
            death_eligible=False,
            permanent_wound_eligible=False,
        )

    _try_interpose(participant, pre_payload)
    _try_companion_defend(participant, pre_payload)
    return None


def apply_damage_to_participant(  # noqa: PLR0913
    participant: CombatParticipant,
    damage: int,
    *,
    force_death: bool = False,
    bypass_pre_apply: bool = False,
    damage_type: DamageType | None = None,
    source: object | None = None,
    source_sheet: CharacterSheet | None = None,
    on_hit_pool: ConsequencePool | None = None,
    delivery: str = StrikeDelivery.MELEE,
    is_area: bool = False,
    execute_missing_health_multiplier: Decimal = Decimal(0),
) -> ParticipantDamageResult:
    """Apply damage to a PC via their CharacterVitals.

    Does NOT roll for knockout/death/wounds — only reports eligibility.
    The caller is responsible for acting on the result.

    When ``source_sheet`` is provided (e.g. PC vs PC damage), increments the
    source's ``damage_dealt`` counter. The target always gets a
    ``damage_received`` increment (regardless of source).

    ``delivery``/``is_area`` (#2209) — NPC callers pass the striking
    ``ThreatPoolEntry.delivery`` and ``targeting_mode != SINGLE``; other
    callers default to MELEE/False. Rampart interception (see
    ``apply_rampart_interception``) runs first, before any other reduction,
    UNLESS ``bypass_pre_apply=True`` (the reflect/retaliation loop guard).

    ``execute_missing_health_multiplier`` (#2643): symmetric sibling of
    :func:`apply_damage_to_opponent`'s same-named kwarg — default 0 (no-op, every
    existing caller unaffected). No live caller passes a nonzero value yet: combat
    technique damage in this codebase only ever resolves against ``CombatOpponent``
    targets (``CombatTechniqueResolver._apply_damage``), never a PC
    ``CombatParticipant`` — this parameter exists so the capability is symmetric and
    directly testable, ready for the day PC-vs-PC technique damage is wired. Uses the
    existing ``health_before_pct`` (captured once, before the condition-damage-
    interaction multiply, and reused for both the execute scaling AND the
    knockout/death classification below it — see :func:`_apply_execute_multiplier`).

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

    if not bypass_pre_apply:
        damage = apply_rampart_interception(
            character,
            damage,
            damage_type,
            attacker_ref=source,
            delivery=delivery,
            is_area=is_area,
        )

    damage_source = classify_source(source)

    # --- DAMAGE_PRE_APPLY (cancellable, amount may be modified) ---
    # bypass_pre_apply=True skips emit + interpose; the bounced-reflect path
    # uses this to terminate re-emission (loop guard). pre_payload is still
    # built so effective_damage derives from it regardless.
    pre_payload = DamagePreApplyPayload(
        target=character,
        amount=damage,
        damage_type=damage_type,
        source=damage_source,
    )
    if not bypass_pre_apply:
        early = _run_pre_apply_interceptors(participant, pre_payload, room, vitals)
        if early is not None:
            return early
    if pre_payload.amount <= 0:
        return ParticipantDamageResult(
            damage_dealt=0,
            health_after=vitals.health,
            knockout_eligible=False,
            death_eligible=False,
            permanent_wound_eligible=False,
        )

    # Deliberate ordering: the on-hit pool (knockback/trap) resolves and may
    # apply its own damage to vitals.health BEFORE the triggering hit's own
    # `vitals.health -= effective_damage` below runs. Both writes land on the
    # same idmapper-cached CharacterVitals instance, so the arithmetic still
    # composes correctly regardless of order (e.g. 100 - 10 hit - 30 trap = 60).
    if on_hit_pool is not None:
        _fire_on_hit_pool(character, source, on_hit_pool)

    # Use the (possibly interposed/modified) amount from the payload.
    # Coerce to int: the MODIFY_PAYLOAD multiply op (DEFEND halves amount by
    # multiplying by 0.5) and INTERPOSE's floor-division both can widen an
    # int amount to float in memory. Django coerces on save, but keeping the
    # in-memory value integral avoids a float flowing through the damage
    # reductions and threshold comparisons below (#1318).
    effective_damage = int(pre_payload.amount)

    # Thread-derived damage reduction (Spec A §5.8 lines 1658–1668).
    # Inlined here rather than a flow subscriber because the flow/event
    # system dispatches on FlowDefinition rows, not Python callables
    # (see Phase 13 Open Item 3). Reads handler caches; near-zero cost.
    from world.conditions.services import resolve_damage_type_resistance  # noqa: PLC0415
    from world.magic.services import apply_damage_reduction_from_threads  # noqa: PLC0415

    effective_damage = apply_damage_reduction_from_threads(character, effective_damage)

    # Damage-type resistance (condition + gift-thread) via the shared seam (#1588).
    # The species drawback's negative ConditionResistanceModifier (vulnerability) and
    # the species-gift thread's positive RESISTANCE pull-effect net here. None
    # damage_type is a no-op. Mirrors the three non-combat damage seams that now call
    # the same function.
    effective_damage = resolve_damage_type_resistance(character, effective_damage, damage_type)

    # Equipped-armor soak (issue #508). PCs have no authored soak field; worn
    # armor is their only soak source, and absorbing pieces take durability wear.
    effective_damage = apply_equipped_armor_soak(character, effective_damage)

    # Attack-cover from PositionShelter (applies_to_attacks=True rows, #2011).
    effective_damage = apply_position_cover(character, effective_damage, damage_type)

    # health_before(_pct) captured HERE, before this hit's own reductions/subtraction
    # below — the PRE-hit basis both the execute multiplier (#2643) and the
    # knockout/death classification further down share. vitals.health is untouched
    # by anything above this line, so this is safe to read early.
    health_before = vitals.health
    if vitals.max_health > 0:
        health_before_pct = max(0.0, health_before / vitals.max_health)
    else:
        health_before_pct = 0.0

    # Condition-damage interactions (#2018). Final percentage multiplier on
    # net damage, after resistance + armor soak. May consume/transform conditions.
    interaction_result = None
    if effective_damage > 0:
        effective_damage, interaction_result = _apply_condition_damage_interactions(
            character, damage_type, effective_damage
        )

    # Execute (#2643): see apply_damage_to_opponent's twin block + docstring.
    effective_damage = _apply_execute_multiplier(
        effective_damage, execute_missing_health_multiplier, health_before_pct
    )

    vitals.health -= effective_damage
    health_after = vitals.health

    if vitals.max_health > 0:
        health_pct = max(0.0, health_after / vitals.max_health)
    else:
        health_pct = 0.0

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

    _emit_post_damage_events(
        character=character,
        room=room,
        effective_damage=effective_damage,
        damage_type=pre_payload.damage_type,
        damage_source=damage_source,
        health_after=health_after,
        knockout_eligible=knockout_eligible,
        was_in_knockout_band=was_in_knockout_band,
        death_eligible=death_eligible,
        force_death=force_death,
    )

    return ParticipantDamageResult(
        damage_dealt=effective_damage,
        health_after=health_after,
        knockout_eligible=knockout_eligible,
        death_eligible=death_eligible,
        permanent_wound_eligible=permanent_wound_eligible,
        damage_interaction=interaction_result,
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
    3. If the slot has a required_archetype (#2022), the action's participant's
       engaged CovenantRole must have nonzero blend weight on that axis (#2529).

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
    # #2022: check required_archetype (a blend-axis label, #2529) if set.
    if slot.required_archetype:
        if not _participant_has_archetype(action.participant, slot.required_archetype):
            return False
    return True


def _participant_has_archetype(participant: CombatParticipant, archetype: str) -> bool:
    """True if an engaged PRIMARY CovenantRole has weight on the given blend axis (#2529).

    ``ComboSlot.required_archetype`` values (SWORD/SHIELD/CROWN) are read as
    blend-axis labels: any engaged PRIMARY role with a nonzero weight on that
    axis satisfies the slot. PRIMARY-only (#2641, Layer 1 — chassis): a
    secondary vow never satisfies a combo slot's archetype requirement.
    """
    covenant_roles = participant.character_sheet.character.covenant_roles
    for role in covenant_roles.currently_engaged_primary_roles():
        if role.blend_weight_for(archetype) > 0:
            return True
    return False


def _try_match_all_slots(
    slots: list[ComboSlot],
    actions: list[CombatRoundAction],
    gift_resonance_ids: dict[int, set[int]],
) -> list[ComboSlotMatch] | None:
    """Try to assign one action per slot using backtracking.

    Returns a list of ``ComboSlotMatch`` if all slots match, or ``None``.
    Backtracking ensures order-independent matching for combos with 2-5 slots.
    """
    # #2051 invariant: combos are never solo — each slot must be filled by a
    # distinct PC-controlled action. CombatRoundAction requires a
    # CombatParticipant (PC) FK; companions materialize as CombatOpponent and
    # cannot produce one. This filter is defense-in-depth against future
    # companion-action surfaces.
    pc_actions = [a for a in actions if a.participant_id is not None]
    actions = pc_actions

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
    # #2051 runtime belt: combos are never solo — skip any definition with fewer
    # than COMBO_MIN_SLOTS slots. Defense-in-depth against legacy/raw-SQL rows
    # that bypassed the admin inline and model clean() guards.
    if not slots or len(slots) < COMBO_MIN_SLOTS:
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
# Combo post-resolution: fused narration + discovery + use-count
# ---------------------------------------------------------------------------


def _process_combo_outcomes(
    action_outcomes: list[ActionOutcome],
    encounter: CombatEncounter,
    round_number: int,  # reserved for future round-scoped narration
) -> list[ActionOutcome]:
    """Post-resolution pass: group combo outcomes, fire narration + discovery.

    Called from ``resolve_round`` after ``_resolve_actions`` returns and
    before ``assess_break_bar``. For each distinct combo that fired:

    1. Broadcast a joint finisher narration naming all contributors (if ≥2).
    2. Fire the discovery ceremony for first-ever triggers.
    3. Increment each contributor's ``ComboLearning.use_count``.
    4. Check for signature flourish unlock.

    Single-contributor combos keep the existing per-PC narration (backward
    compatible — the per-PC ``_record_and_broadcast_pc_action`` already ran).
    """
    from collections import defaultdict  # noqa: PLC0415

    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        render_combo_finisher_narration,
    )
    from world.combat.models import ComboLearning  # noqa: PLC0415

    # Group outcomes by combo_used.
    combo_groups: dict[int, list[tuple[ActionOutcome, CombatParticipant]]] = defaultdict(list)
    for outcome in action_outcomes:
        if outcome.combo_used is not None and outcome.participant_id is not None:
            participant = CombatParticipant.objects.filter(pk=outcome.participant_id).first()
            if participant is not None:
                combo_groups[outcome.combo_used.pk].append((outcome, participant))

    for group in combo_groups.values():
        combo = group[0][0].combo_used
        participant_sheets = [p.character_sheet for _, p in group]

        # 1. Joint finisher narration (only for multi-contributor combos).
        _MULTI_CONTRIBUTOR_THRESHOLD = 2
        if len(group) >= _MULTI_CONTRIBUTOR_THRESHOLD:
            contributor_labels = [str(p) for _, p in group]
            total_damage = sum(
                dr.damage_dealt for outcome, _ in group for dr in outcome.damage_results
            )
            # Determine target label from the first outcome's action.
            target_label = None
            for _outcome, participant in group:
                action = CombatRoundAction.objects.filter(
                    participant=participant,
                    round_number=round_number,
                ).first()
                if action and action.focused_opponent_target_id:
                    target_label = action.focused_opponent_target.name
                    break

            signature_clause = _signature_clause_for(combo)
            narration = render_combo_finisher_narration(
                combo_name=combo.name,
                contributor_labels=contributor_labels,
                target_label=target_label,
                total_damage=total_damage,
                signature_clause=signature_clause,
            )
            broadcast_action_outcome(encounter=encounter, narration=narration)

        # 2. Fire discovery ceremony for first-ever triggers.
        was_known = ComboLearning.objects.filter(
            combo=combo,
            character_sheet__in=participant_sheets,
        ).exists()
        if not was_known and combo.discoverable_via_combat:
            from world.combat.combo_discovery import fire_combo_discovery  # noqa: PLC0415

            fire_combo_discovery(
                combo=combo,
                participant_sheets=participant_sheets,
                scene=encounter.scene,
            )

        # 3. Increment use_count for each contributor.
        for sheet in participant_sheets:
            ComboLearning.objects.filter(
                combo=combo,
                character_sheet=sheet,
            ).update(use_count=F("use_count") + 1)

    return action_outcomes


def _signature_clause_for(
    combo: ComboDefinition,
) -> str | None:
    """Return the signature flourish clause if unlocked, else None.

    Checks for a ``ComboSignature`` row matching the combo. If one exists,
    sums ``use_count`` across covenant members who know the combo and checks
    against ``unlock_threshold``.
    """
    from world.combat.models import ComboSignature  # noqa: PLC0415

    signatures = ComboSignature.objects.filter(combo=combo).select_related("covenant")
    for sig in signatures:
        # Sum use_count across all covenant members who know this combo.
        total_uses = (
            ComboLearning.objects.filter(
                combo=combo,
                character_sheet__combat_participations__covenant_role__covenant=sig.covenant,
            ).aggregate(total=Sum("use_count"))["total"]
            or 0
        )

        if total_uses >= sig.unlock_threshold and sig.flourish_narrative:
            return sig.flourish_narrative

    return None


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

    #2536 slice 3 Task 6: this is the ONLY defense-check site in v1 that
    threads a ``SituationContext`` with ``attacker`` populated
    (``opponent_action.opponent``) into ``perform_check`` — making
    CHECK_BONUS/TIER_FLOOR/BOTCH_IMMUNITY situational perks, including
    ``Situation.ATTACKER_AFFINITY``-gated ones, live on the defender's roll.

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

    # Route the defensive check through the shared modifier seam so it honors
    # every character-side source — fashion (perception-relative, scene-derived),
    # covenant-role / equipment-walk, persistent CharacterModifiers, and
    # conditions — exactly as the offense roll does (#750, #512). The perceiving
    # society is derived from the encounter's scene; ``collect_check_modifiers``
    # self-limits (a fashion bonus only lands when ``check_type`` has a scoped
    # modifier_target and the scene's society has a matching in-vogue style).
    # Bond combat bonus (#2021): relationship co-combatant passive.
    from world.relationships.services import bond_combat_bonus  # noqa: PLC0415

    bond_contributions = bond_combat_bonus(
        participant.character_sheet,
        participant.encounter,
    )

    # Wind-as-mechanic (#1555) symmetry: the same gale that ruins a PC's
    # missile shot ruins an NPC's. Only MISSILE-delivered threat entries with
    # a defense roll are affected — flat base_damage entries (no defense_check_type,
    # never reaching this function) stay untouched.
    if (
        opponent_action.threat_entry.delivery == StrikeDelivery.MISSILE
        and participant.encounter.room is not None
    ):
        from world.locations.constants import StatKey  # noqa: PLC0415
        from world.locations.services import felt_exposure  # noqa: PLC0415

        wind_mod = wind_penalty(felt_exposure(participant.encounter.room, stat_key=StatKey.WIND))
        if wind_mod:
            bond_contributions = [
                *bond_contributions,
                ModifierContribution(
                    source_kind=ModifierSourceKind.SCENE,
                    source_label="Wind",
                    value=-wind_mod,
                ),
            ]

    breakdown = collect_check_modifiers(
        participant.character_sheet,
        check_type,
        scene=participant.encounter.scene,
        extra_contributions=bond_contributions,
    )

    # #2536 slice 3 Task 6: thread the defense-side situation context so
    # CHECK_BONUS/TIER_FLOOR/BOTCH_IMMUNITY situational perks can fire on the
    # PC's defensive roll — the one context where the SUBJECT is not the
    # aggressor, so `target` stays None and `attacker` carries the NPC's
    # opponent row instead (the ATTACKER_AFFINITY evaluator's data source).
    # Mirrors the offense sites' sheet + CombatRoundContext construction
    # (services.py:435-448) with `holder`/`subject` both the defender's own
    # sheet, matching `_resolve_social_check`'s pattern above.
    from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
    from world.covenants.perks.context import SituationContext  # noqa: PLC0415

    defender_sheet = participant.character_sheet
    situation_ctx = SituationContext(
        holder=defender_sheet,
        subject=defender_sheet,
        target=None,
        resolution=CombatRoundContext(participant),
        attacker=opponent_action.opponent,
    )
    result: CheckResult = perform_check_fn(
        character,
        check_type,
        extra_modifiers=breakdown.total,
        situation_ctx=situation_ctx,
    )

    multiplier = _damage_multiplier_for_success(result.success_level)
    # damage_multiplier is a Decimal field (authored per-opponent scaling);
    # damage_scale (#2637, the wind-up downgrade ladder) is a plain float —
    # apply them in two steps so Decimal never multiplies directly against a
    # float (TypeError).
    base_damage = int(
        opponent_action.threat_entry.base_damage * opponent_action.opponent.damage_multiplier
    )
    base_damage = int(base_damage * opponent_action.damage_scale)
    final_damage = math.floor(base_damage * multiplier)

    damage_result = apply_damage_to_participant(
        participant,
        final_damage,
        damage_type=opponent_action.threat_entry.damage_type,
        source=opponent_action.opponent,
        on_hit_pool=opponent_action.threat_entry.on_hit_consequence_pool,
        delivery=opponent_action.threat_entry.delivery,
        is_area=opponent_action.threat_entry.targeting_mode != TargetingMode.SINGLE,
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
            _apply_phase_transition(opponent, phase)
            _spawn_reinforcements(opponent.encounter, phase)
            return phase

    return None


def _apply_phase_transition(opponent: CombatOpponent, phase: BossPhase) -> None:
    """Stamp all phase-sourced fields onto the opponent and save."""
    opponent.current_phase = phase.phase_number
    if phase.threat_pool_id:
        opponent.threat_pool = phase.threat_pool
    opponent.soak_value = phase.soak_value
    opponent.probing_current = 0
    if phase.probing_threshold is not None:
        opponent.probing_threshold = phase.probing_threshold
    _stamp_enrage(opponent, phase)
    _stamp_break_bar(opponent, phase)
    opponent.save(
        update_fields=[
            "current_phase",
            "threat_pool_id",
            "soak_value",
            "probing_current",
            "probing_threshold",
            "damage_multiplier",
            "actions_per_round",
            "break_bar_threshold",
            "break_bar_current",
            "vulnerability_rounds",
            "vulnerability_intensity_bonus",
            "vulnerability_rounds_remaining",
        ],
    )


def _stamp_enrage(opponent: CombatOpponent, phase: BossPhase) -> None:
    """Stamp damage multiplier and actions_per_round from phase config."""
    opponent.damage_multiplier = phase.damage_multiplier
    if phase.actions_per_round is not None:
        opponent.actions_per_round = phase.actions_per_round + phase.extra_actions
    else:
        opponent.actions_per_round = opponent.actions_per_round + phase.extra_actions


def _stamp_break_bar(opponent: CombatOpponent, phase: BossPhase) -> None:
    """Reset the break bar from the new phase's break-bar config.

    Re-applies the pacing floor (#2642) on top of the phase's authored
    threshold — ``_stamp_phase_break_bar_config`` already clamps it at clone
    time, but this keeps the invariant self-evident at the site that actually
    writes the opponent's live ``break_bar_threshold`` on a phase transition.
    """
    if phase.break_bar_threshold > 0:
        threshold = max(phase.break_bar_threshold, minimum_break_bar_threshold())
        opponent.break_bar_threshold = threshold
        opponent.break_bar_current = threshold
        opponent.vulnerability_rounds = phase.vulnerability_rounds
        opponent.vulnerability_intensity_bonus = phase.vulnerability_intensity_bonus
        opponent.vulnerability_rounds_remaining = 0
    else:
        opponent.break_bar_threshold = 0
        opponent.break_bar_current = 0
        opponent.vulnerability_rounds_remaining = 0


def _spawn_reinforcements(encounter: CombatEncounter, phase: BossPhase) -> None:
    """Spawn reinforcement adds on phase entry."""
    if phase.reinforcement_template_id is None or phase.reinforcement_count <= 0:
        return
    for _ in range(phase.reinforcement_count):
        add_opponent(
            encounter,
            name=phase.reinforcement_template.name,
            tier=phase.reinforcement_template.tier,
            threat_pool=phase.reinforcement_template.threat_pool,
            max_health=20,
            auto_phases=False,
        )


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


# ---------------------------------------------------------------------------
# Social/mental combat verb resolution (#2015)
# ---------------------------------------------------------------------------


def _social_combat_difficulty(
    target: CombatOpponent | None,
    *,
    effort_level: str = "medium",
) -> int:
    """Compute the target_difficulty for a social-combat check (#2015).

    Composure defense: ``compute_resist_increment`` (the same path scenes use,
    now wired into combat for the first time). Mindless resistance: a mindless
    target adds ``MINDLESS_MORALE_RESISTANCE`` — a high resistance tier, not a
    wall. Returns 0 when there is no target (rally targets an ally).
    """
    if target is None:
        return 0

    from world.checks.services import compute_resist_increment  # noqa: PLC0415
    from world.combat.constants import MINDLESS_MORALE_RESISTANCE  # noqa: PLC0415
    from world.combat.morale import tier_has_morale  # noqa: PLC0415

    difficulty = 0
    if target.objectdb is not None:
        difficulty = compute_resist_increment(target.objectdb, effort_level)
    if not tier_has_morale(target):
        difficulty += MINDLESS_MORALE_RESISTANCE
    return difficulty


def _resolve_social_check(
    participant: CombatParticipant,
    check_type_name: str,
    target_difficulty: int,
    target: CharacterSheet | None = None,
) -> int:
    """Roll a social-combat check and return the success_level (#2015).

    Resolves the CheckType by name (seeded by social_combat_content). Routes
    modifiers through ``collect_check_modifiers`` (the same seam combat uses),
    then ``perform_check``. Returns ``check_result.success_level``.

    ``target`` (#2536 Task 6 fold-in fix, extended to Parley on review): the
    acting participant's declared opponent, when this social action has one
    — threaded into ``SituationContext.target`` so target-keyed CHECK_BONUS
    perks (``TARGET_DISTRACTED``/``TARGET_SWAYED_BY_ALLY``/
    ``TARGET_FOCUSED_ELSEWHERE``/``TARGET_FAVORABLY_DISPOSED``) can fire on
    Demoralize/Taunt/Parley, whose callers all resolve
    ``_resolve_primary_target_sheet(action)`` and pass it through. Rally
    (targets an ally, not an opponent) keeps the default ``None`` — it has no
    opposing target for a TARGET_* situation to key off.
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import collect_check_modifiers, perform_check  # noqa: PLC0415
    from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
    from world.covenants.perks.context import SituationContext  # noqa: PLC0415

    check_type = CheckType.objects.filter(name=check_type_name, is_active=True).first()
    if check_type is None:
        return 0

    character = participant.character_sheet.character
    breakdown = collect_check_modifiers(
        participant.character_sheet, check_type, scene=participant.encounter.scene
    )
    # #2536 Task 5 review fix (Task 6: now target-threaded for callers that
    # have one — see the docstring above): thread the live round context so
    # CHECK_BONUS situational perks can fire on Rally/Demoralize/Taunt/Parley.
    situation_ctx = SituationContext(
        holder=participant.character_sheet,
        subject=participant.character_sheet,
        target=target,
        resolution=CombatRoundContext(participant),
    )
    result = perform_check(
        character,
        check_type,
        target_difficulty=target_difficulty,
        extra_modifiers=breakdown.total,
        situation_ctx=situation_ctx,
    )
    return result.success_level or 0


def _resolve_rally(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> ActionOutcome:
    """Resolve a declared rally — inspire an ally (#2015).

    Rolls the Rally check (presence + Performance + Oratory). On success, applies
    a short-lived ``Inspired`` condition to the ally. On a great success (SL>=3),
    also restores morale to ally-side summon opponents.
    """
    from world.combat.constants import (  # noqa: PLC0415
        RALLY_BASE_DIFFICULTY,
        RALLY_GREAT_SUCCESS_LEVEL,
        RALLY_MORALE_PER_LEVEL,
    )
    from world.combat.social_combat_content import INSPIRED_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415

    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))

    success_level = _resolve_social_check(participant, "Rally", RALLY_BASE_DIFFICULTY)
    if success_level >= 1:
        ally = action.focused_ally_target
        if ally is not None:
            # Apply Inspired condition to the ally.
            inspired = ConditionTemplate.objects.filter(name=INSPIRED_CONDITION_NAME).first()
            if inspired is not None:
                apply_condition(
                    ally.character_sheet.character,
                    inspired,
                    source_character=participant.character_sheet.character,
                    source_description="Rallied in combat.",
                )

            # Great success: restore morale to ally-side summon opponents.
            if success_level >= RALLY_GREAT_SUCCESS_LEVEL:
                restore = success_level * RALLY_MORALE_PER_LEVEL
                ally_summons = CombatOpponent.objects.filter(
                    encounter=participant.encounter,
                    status=OpponentStatus.ACTIVE,
                    allegiance=CombatAllegiance.ALLY,
                )
                for opp in ally_summons:
                    opp.morale = min(opp.max_morale, opp.morale + restore)
                    opp.save(update_fields=["morale"])

    return outcome


def _resolve_demoralize(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> ActionOutcome:
    """Resolve a declared demoralize — break an opponent's nerve (#2015).

    Rolls the Demoralize check (presence + Persuasion + Intimidation) against the
    target's Composure (+ mindless resistance). On success, depletes morale.
    """
    from world.combat.constants import DEMORALIZE_MORALE_PER_LEVEL  # noqa: PLC0415
    from world.combat.morale import apply_morale_damage, tier_has_morale  # noqa: PLC0415

    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))

    target = action.focused_opponent_target
    if target is None:
        return outcome

    target_difficulty = _social_combat_difficulty(target)
    success_level = _resolve_social_check(
        participant, "Demoralize", target_difficulty, target=_resolve_primary_target_sheet(action)
    )

    if success_level < 1:
        # Failed: mindless targets narrate "the construct is unmoved."
        if not tier_has_morale(target):
            outcome.summary = "The construct is unmoved."
        return outcome

    apply_morale_damage(target, success_level * DEMORALIZE_MORALE_PER_LEVEL)
    return outcome


def _resolve_taunt(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> ActionOutcome:
    """Resolve a declared taunt — draw an NPC's aggro (#2015).

    Rolls the Taunt check (wits + Persuasion + Intimidation) against the target's
    Composure. On success, accumulates threat on the existing ThreatRecord seam.
    """
    from world.combat.constants import TAUNT_THREAT_PER_LEVEL  # noqa: PLC0415

    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))

    target = action.focused_opponent_target
    if target is not None:
        target_difficulty = _social_combat_difficulty(target)
        success_level = _resolve_social_check(
            participant, "Taunt", target_difficulty, target=_resolve_primary_target_sheet(action)
        )

        if success_level >= 1:
            accumulate_threat(
                participant.encounter,
                target,
                participant,
                success_level * TAUNT_THREAT_PER_LEVEL,
            )

    return outcome


def _resolve_parley(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> ActionOutcome:
    """Resolve a declared parley — talk a foe down mid-fight (#2015).

    Rolls the Parley check (charm + Persuasion + Seduction) against the target's
    Composure (+ mindless resistance — a breakthrough grants a fleeting mind). On
    success, routes through ``apply_social_disposition_delta``. On a decisive
    success (SL>=3), calms the opponent. On a critical success (SL>=5) against a
    broken opponent, the NPC yields (FLED).
    """
    from world.combat.constants import (  # noqa: PLC0415
        PARLEY_CRITICAL_SUCCESS_LEVEL,
        PARLEY_DECISIVE_SUCCESS_LEVEL,
        OpponentStatus,
    )
    from world.combat.morale import (  # noqa: PLC0415
        OpponentMoraleState,
        morale_state_for,
        tier_has_morale,
    )
    from world.conditions.constants import CALM_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415
    from world.npc_services.social_disposition import (  # noqa: PLC0415
        apply_social_disposition_delta,
    )

    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))

    target = action.focused_opponent_target
    if target is None:
        return outcome

    target_difficulty = _social_combat_difficulty(target)
    success_level = _resolve_social_check(
        participant, "Parley", target_difficulty, target=_resolve_primary_target_sheet(action)
    )

    if success_level < 1:
        # Failed: mindless targets narrate "it has no mind to reach."
        if not tier_has_morale(target):
            outcome.summary = "It has no mind to reach."
        return outcome

    # Success: apply the disposition delta (the built path, now reachable in combat).
    actor = participant.character_sheet.character
    target_persona_id = target.persona_id
    if target_persona_id is not None:
        apply_social_disposition_delta(actor, target_persona_id, _ParleyResult(success_level))

    # Decisive success: calm the opponent (Calm condition -> NEUTRAL allegiance).
    # Boss sway resistance (#2642): a BOSS-tier opponent resists — it requires
    # one success-level step above the normal decisive threshold. Court-tier
    # NPCs (the majority) calm at the unmodified threshold.
    required_decisive_level = PARLEY_DECISIVE_SUCCESS_LEVEL
    if target.tier == OpponentTier.BOSS:
        required_decisive_level += BOSS_PARLEY_RESISTANCE_STEP
    if success_level >= required_decisive_level and target.objectdb is not None:
        calm = ConditionTemplate.objects.filter(name=CALM_CONDITION_NAME).first()
        if calm is not None:
            apply_condition(
                target.objectdb,
                calm,
                source_character=actor,
                source_description="Parleyed into calm.",
            )

    # Critical success against a broken opponent: the NPC yields (FLED, alive).
    if (
        success_level >= PARLEY_CRITICAL_SUCCESS_LEVEL
        and morale_state_for(target) == OpponentMoraleState.BREAK
    ):
        target.status = OpponentStatus.FLED
        target.save(update_fields=["status"])

    return outcome


@dataclass
class _ParleyResult:
    """Minimal result shim so apply_social_disposition_delta can read success_level.

    The disposition service reads ``result.main_result.check_result.success_level``;
    this shim provides that shape without constructing a full PendingResolution.
    """

    main_result: _ParleyMainResult

    def __init__(self, success_level: int) -> None:
        self.main_result = _ParleyMainResult(success_level)


@dataclass
class _ParleyMainResult:
    check_result: _ParleyCheckResult

    def __init__(self, success_level: int) -> None:
        self.check_result = _ParleyCheckResult(success_level)


@dataclass
class _ParleyCheckResult:
    success_level: int


def _resolve_charge_movement(participant: CombatParticipant, action: CombatRoundAction) -> None:
    """Move *participant*'s character onto the CHARGE target's position (#1843).

    Called unconditionally at resolution time — reachability was already
    validated at declaration (``declare_charge``), but the round may have
    moved other combatants since; force-moving unconditionally here mirrors
    the existing Guardian blink-protect call site
    (``world.areas.positioning.services.force_move_to_position``) rather than
    re-validating and potentially fizzling a declared charge on a stale check.
    No-ops when either side is unpositioned (lenient, matches declare-time).
    """
    from world.areas.positioning.services import (  # noqa: PLC0415
        force_move_to_position,
        position_of,
    )

    target = action.focused_opponent_target
    if target is None or target.objectdb is None:
        return
    dest = position_of(target.objectdb)
    if dest is None:
        return
    rider = participant.character_sheet.character
    if position_of(rider) is None:
        return
    force_move_to_position(rider, dest)


def _joust_offense_check(participant: CombatParticipant, action: CombatRoundAction) -> CheckResult:
    """Roll one side's JOUST offense check via the shared CombatTechniqueResolver seam.

    Reuses ``CombatTechniqueResolver._roll_check`` so EFFORT/PULL/bond bonuses
    and the LANCE_UNMOUNTED_PENALTY gate all compose exactly as they would for
    a normal attack (both jousters are validated Mounted+LANCE at declare
    time, so the unmounted-lance penalty never actually fires here).
    """
    from world.magic.services.anima import resolve_cast_check_type  # noqa: PLC0415

    technique = action.focused_action
    template = technique.action_template
    if template is None:
        raise ActionDispatchError(ActionDispatchError.TECHNIQUE_NOT_COMBAT_READY)
    offense_check_type = resolve_cast_check_type(participant.character_sheet.character, template)
    resolver = CombatTechniqueResolver(
        participant=participant,
        action=action,
        pull_flat_bonus=0,
        fatigue_category=action.focused_category or ActionCategory.PHYSICAL,
        offense_check_type=offense_check_type,
        offense_check_fn=None,
    )
    return resolver._roll_check()  # noqa: SLF001 - same-module reuse of the shared roll seam


def _resolve_joust_pass(
    participant: CombatParticipant,
    action: CombatRoundAction,
    other: CombatParticipant,
    other_action: CombatRoundAction,
) -> None:
    """Resolve a JOUST's single opposed pass — grades by the success_level gap (#1843).

    decisive gap (>= JOUST_DECISIVE_MARGIN): loser takes the winner's lance
    weapon damage x2 + the Unhorsed condition, which force-dismounts them.
    narrow gap (>= JOUST_NARROW_MARGIN, < decisive): loser takes the winner's
    lance weapon damage x1, keeps the saddle. Tie (gap 0): both jarred, no
    damage. Damage is applied to the loser's mirror CombatOpponent via
    ``apply_damage_to_opponent`` — the same non-bypassing pipeline every
    normal duel attack already uses (defenses/soak/non-lethal PvP capping,
    ADR-0023, all fire unchanged).
    """
    from world.companions.mount_content import UNHORSED_CONDITION_NAME  # noqa: PLC0415
    from world.companions.services import MountError, dismount_companion  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415

    check_a = _joust_offense_check(participant, action)
    check_b = _joust_offense_check(other, other_action)
    gap = check_a.success_level - check_b.success_level

    if gap == 0:
        return  # tie — both jarred, no damage

    winner, loser = (participant, other) if gap > 0 else (other, participant)
    margin = abs(gap)

    weapon = effective_weapon_profile(winner.character_sheet.character)
    base_damage = weapon.damage if weapon is not None else 0

    loser_mirror = CombatOpponent.objects.filter(
        encounter=participant.encounter, mirrors_participant=loser
    ).first()
    if loser_mirror is None:
        return

    if margin >= JOUST_DECISIVE_MARGIN:
        apply_damage_to_opponent(
            loser_mirror,
            base_damage * 2,
            damage_type=weapon.damage_type if weapon is not None else None,
            source_sheet=winner.character_sheet,
        )
        unhorsed = ConditionTemplate.get_by_name(UNHORSED_CONDITION_NAME)
        apply_condition(
            loser.character_sheet.character,
            unhorsed,
            source_character=winner.character_sheet.character,
        )
        with contextlib.suppress(MountError):
            # Not actually mounted somehow — nothing to dismount.
            dismount_companion(loser.character_sheet)
    else:
        apply_damage_to_opponent(
            loser_mirror,
            base_damage,
            damage_type=weapon.damage_type if weapon is not None else None,
            source_sheet=winner.character_sheet,
        )


def _resolve_joust(participant: CombatParticipant, action: CombatRoundAction) -> ActionOutcome:
    """Dispatch a declared JOUST maneuver — resolves once both duelists have declared it.

    Deterministic single-resolution: only the lower-pk participant's call
    actually runs ``_resolve_joust_pass`` (avoids a schema field just to
    memoize "already resolved this round" — the higher-pk participant's own
    ``_resolve_pc_action`` pass is a no-op once its partner's pass already
    applied both sides' outcomes).
    """
    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))
    outcome.participant_id = participant.pk

    other = (
        CombatParticipant.objects.filter(encounter=participant.encounter)
        .exclude(pk=participant.pk)
        .select_related("character_sheet")
        .first()
    )
    if other is not None:
        other_action = CombatRoundAction.objects.filter(
            participant=other, round_number=action.round_number
        ).first()
        if (
            other_action is not None
            and other_action.maneuver == CombatManeuver.JOUST
            and participant.pk <= other.pk
        ):
            _resolve_joust_pass(participant, action, other, other_action)

    return outcome


def _resolve_use_item(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> ActionOutcome:
    """Resolve a USE_ITEM combat maneuver by dispatching UseItemAction (#2023, #2120).

    Reuses the built UseItemAction machinery (prerequisites, effect application)
    rather than duplicating it. The item is resolved from the action's
    ``item_instance`` FK; the actor is the participant's character. Using an
    item costs the round's focused action — it is a primary maneuver, mutually
    exclusive with ``focused_action``, like FLEE/COVER/INTERPOSE.

    Two bugs fixed here (#2120): (1) the declared target was never forwarded,
    so any on-use item with a non-null ``on_use_target_kind`` (e.g. a healing
    potion used on an ally) silently self-targeted — ``focused_ally_target``/
    ``focused_opponent_target`` are now threaded through as ``target``. (2)
    ``UseItemAction`` expects an ``ObjectDB`` for its ``item`` kwarg
    (``resolve_item_instance`` walks ``target.item_instance``), but this used
    to pass the ``ItemInstance`` row itself — now resolved to its
    ``game_object`` first.
    """
    from actions.definitions.items import UseItemAction  # noqa: PLC0415

    outcome = ActionOutcome(
        entity_type=ENTITY_TYPE_PC,
        entity_label=str(participant),
    )
    outcome.participant_id = participant.pk

    if action.item_instance is not None:
        item_object = action.item_instance.game_object
        if item_object is not None:
            character = participant.character_sheet.character
            target: ObjectDB | None = None
            if action.focused_ally_target is not None:
                target = action.focused_ally_target.character_sheet.character
            elif action.focused_opponent_target is not None:
                target = action.focused_opponent_target.objectdb

            UseItemAction().run(actor=character, item=item_object, target=target)
            # UseItemAction's effects (healing, conditions) are applied by the action
            # itself; the combat round just needs to know the maneuver resolved.

    return outcome


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
    # Bond combat bonus (#2021): relationship co-combatant passive.
    from world.relationships.services import bond_combat_bonus  # noqa: PLC0415

    extra_contributions.extend(bond_combat_bonus(participant.character_sheet, encounter))
    breakdown = collect_check_modifiers(
        participant.character_sheet,
        config.check_type,
        scene=encounter.scene,
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


def _record_and_broadcast_pc_action(  # noqa: PLR0913
    *,
    participant: CombatParticipant,
    action: CombatRoundAction,
    technique: Technique,
    target: CombatOpponent | None,
    outcome: ActionOutcome,
    combat_result: CombatTechniqueResult | None,
) -> None:
    """Record the ACTION-mode Interaction and broadcast the outcome narration."""
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        create_action_interaction,
        render_action_declaration_label,
        render_action_outcome_narration,
    )
    from world.scenes.interaction_services import push_interaction  # noqa: PLC0415

    # Only the attack path returns a CombatTechniqueResult (which carries fury);
    # the non-attack path returns a CombatTechniqueResolution with no fury field.
    fury_committed = (
        combat_result.fury_committed if isinstance(combat_result, CombatTechniqueResult) else None
    )
    interaction = create_action_interaction(
        participant=participant,
        round_number=action.round_number,
        summary_label=render_action_declaration_label(action),
        fury_committed=fury_committed,
    )
    if interaction is not None:
        action.interaction = interaction
        action.interaction_timestamp = interaction.timestamp
        action.save(update_fields=["interaction", "interaction_timestamp"])
        push_interaction(interaction)
        if combat_result is not None:
            from world.scenes.power_ledger_services import persist_power_ledger  # noqa: PLC0415

            persist_power_ledger(interaction=interaction, ledger=combat_result.power_ledger)

    from world.magic.services.signature_effects import resolve_signature_snippet  # noqa: PLC0415

    target_label = target.name if target is not None else None
    signature_snippet = resolve_signature_snippet(participant.character_sheet.character, technique)
    interaction_result = next(
        (dr.damage_interaction for dr in outcome.damage_results if dr.damage_interaction),
        None,
    )
    narration = render_action_outcome_narration(
        actor_label=str(participant),
        technique_name=technique.name,
        target_label=target_label,
        outcome=outcome,
        power_ledger=combat_result.power_ledger if combat_result is not None else None,
        signature_snippet=signature_snippet,
        interaction_result=interaction_result,
    )
    broadcast_action_outcome(encounter=participant.encounter, narration=narration)


def _maybe_suggest_entrance_dramatic_moment(
    participant: CombatParticipant,
    combat_result: CombatTechniqueResult,
) -> None:
    """Fire the #2183 dramatic-moment suggestion for a resolved entrance-declared cast.

    The combat-round sibling of ``run_entrance_success_hooks``'s suggestion half —
    fired here (not at declaration time) because the real success level is only known
    once the declared cast actually resolves. Best-effort: a suggestion failure must
    never break round resolution.
    """
    if not combat_result.technique_use_result.confirmed:
        return
    resolution = combat_result.technique_use_result.resolution_result
    if not isinstance(resolution, CombatTechniqueResolution):
        return
    try:
        from world.magic.services.gain import maybe_suggest_dramatic_moments  # noqa: PLC0415

        maybe_suggest_dramatic_moments(
            character_sheet=participant.character_sheet,
            scene=participant.encounter.scene,
            success_level=resolution.check_result.success_level,
            interaction=None,
        )
    except Exception:
        logger.exception(
            "Failed to suggest a dramatic moment for entrance-declared cast (participant_id=%s)",
            participant.pk,
        )


def _maybe_produce_insight_for_cast(
    participant: CombatParticipant,
    combat_result: CombatTechniqueResult,
    technique: Technique,
) -> None:
    """Fire the #2645 Insight rider after a successful combat cast resolution.

    Mirrors ``_maybe_suggest_entrance_dramatic_moment``'s isolation: an
    Insight failure must never break round resolution. Also mirrors
    ``_record_and_broadcast_pc_action``'s ``isinstance`` guard — only the
    attack path returns a full ``CombatTechniqueResult`` (which carries
    ``technique_use_result``); a routing-isolation test double (or a future
    non-attack path) can hand back a bare ``CombatTechniqueResolution``.
    """
    if not isinstance(combat_result, CombatTechniqueResult):
        return
    if not combat_result.technique_use_result.confirmed:
        return
    try:
        from world.covenants.insight import maybe_produce_insight  # noqa: PLC0415

        maybe_produce_insight(
            caster_sheet=participant.character_sheet,
            technique=technique,
            resolution_participant=participant,
        )
    except Exception:
        logger.exception(
            "Failed to produce an Insight for a combat cast (participant_id=%s)",
            participant.pk,
        )


def _run_combat_technique_pipeline(
    participant: CombatParticipant,
    action: CombatRoundAction,
    technique: Technique,
    fatigue_category: str,
    offense_check_fn: PerformCheckFn | None,
) -> CombatTechniqueResult:
    """Run the magic combat-technique pipeline for a single focused action.

    Derives the ``offense_check_type`` from the technique's action_template
    and resolves it via ``resolve_combat_technique``. Raises
    ``ActionDispatchError(TECHNIQUE_NOT_COMBAT_READY)`` if the technique has
    no action_template (not configured for combat use).
    """
    template = technique.action_template
    if template is None:
        raise ActionDispatchError(ActionDispatchError.TECHNIQUE_NOT_COMBAT_READY)
    from world.magic.services.anima import resolve_cast_check_type  # noqa: PLC0415

    return resolve_combat_technique(
        participant=participant,
        action=action,
        fatigue_category=fatigue_category,
        offense_check_type=resolve_cast_check_type(participant.character_sheet.character, template),
        offense_check_fn=offense_check_fn,
    )


def _apply_combo_rider(
    participant: CombatParticipant,
    action: CombatRoundAction,
    target: CombatOpponent,
    outcome: ActionOutcome,
) -> None:
    """Append combo-upgraded bonus damage when the target is still alive.

    The combo rider is applied in addition to the pipeline result. It is
    skipped when the target has been defeated (by the pipeline or earlier).
    """
    target.refresh_from_db()
    if target.status == OpponentStatus.DEFEATED:
        return
    combo = action.combo_upgrade
    dmg_result = apply_damage_to_opponent(
        target,
        combo.bonus_damage,
        bypass_soak=combo.bypass_soak,
        source_sheet=participant.character_sheet,
    )
    outcome.combo_used = combo
    outcome.damage_results.append(dmg_result)


def _maybe_record_npc_regard_on_defeat(
    participant: CombatParticipant,
    action: CombatRoundAction,
    target: CombatOpponent | None,
    outcome: ActionOutcome,
) -> None:
    """Record a PC_FOILED_NPC_PLAN regard event when a PC defeats a notable NPC.

    #2039 — a persona-backed NPC opponent defeated by a PC records a regard
    event. A mook/persona-less opponent's defeat is deliberately a no-op.
    """
    if target is None or target.persona_id is None:
        return
    defeated = any(
        dr.opponent_id == target.pk and dr.defeated
        for dr in outcome.damage_results
        if hasattr(dr, "opponent_id")
    )
    if not defeated:
        return
    from world.npc_services.constants import NpcRegardEventReason  # noqa: PLC0415
    from world.npc_services.regard import (  # noqa: PLC0415
        get_regard_event_config,
        record_npc_regard_event,
    )
    from world.scenes.models import Persona  # noqa: PLC0415

    try:
        pc_persona = participant.character_sheet.primary_persona
    except Persona.DoesNotExist:
        pc_persona = None
    if pc_persona is not None:
        cfg = get_regard_event_config()
        record_npc_regard_event(
            holder_persona=target.persona,
            target=pc_persona,
            amount=cfg.combat_defeat_amount,
            reason=NpcRegardEventReason.PC_FOILED_NPC_PLAN,
            source_pc_combat_action=action,
        )


def _resolve_pc_action(  # noqa: C901, PLR0911, PLR0912
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

    # Social/mental combat verbs (#2015): resolve as checks at round-tick.
    if action.maneuver == CombatManeuver.RALLY:
        return _resolve_rally(participant, action)
    if action.maneuver == CombatManeuver.DEMORALIZE:
        return _resolve_demoralize(participant, action)
    if action.maneuver == CombatManeuver.TAUNT:
        return _resolve_taunt(participant, action)
    if action.maneuver == CombatManeuver.PARLEY:
        return _resolve_parley(participant, action)

    # On-use items as a combat maneuver (#2023): dispatches the existing
    # UseItemAction as a primary maneuver (mutually exclusive with the
    # focused technique, like FLEE/COVER). Using an item costs the
    # round's focused action.
    if action.maneuver == CombatManeuver.USE_ITEM:
        return _resolve_use_item(participant, action)

    # JOUST (#1843): a bilateral opposed pass between two mounted, lance-armed
    # duelists — resolved directly against the loser's mirror CombatOpponent,
    # not through the normal per-target technique pipeline below (there is no
    # single "attacker vs one opponent" shape here). Returns immediately.
    if action.maneuver == CombatManeuver.JOUST:
        return _resolve_joust(participant, action)

    # CHARGE (#1843): closes distance to the declared opponent, THEN falls
    # through to the normal weapon-attack pipeline below (no early return) —
    # CHARGE augments a normal attack via CombatTechniqueResolver's
    # CHARGE_CHECK_BONUS/CHARGE_DAMAGE_BONUS injection, it doesn't replace it.
    if action.maneuver == CombatManeuver.CHARGE:
        _resolve_charge_movement(participant, action)

    # YIELD ends a duel immediately: the yielding PC loses. Passives-only outcome;
    # _resolve_duel_completion is a no-op afterwards because the encounter is now
    # COMPLETED (yield_duel routes through complete_encounter).
    # Guard: only valid in a DUEL encounter — a YIELD in any other encounter type
    # is a no-op (treated like a passives-only round, same as COVER).
    if (
        action.maneuver == CombatManeuver.YIELD
        and participant.encounter.encounter_type == EncounterType.DUEL
    ):
        from world.combat.duels import yield_duel  # noqa: PLC0415

        yield_duel(participant)
        return ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))

    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))
    outcome.participant_id = participant.pk

    technique = action.focused_action
    if technique is None:
        # Passives-only round (e.g. flee) — no focused action to resolve.
        return outcome

    outcome.effect_type_id = technique.effect_type_id

    target = action.focused_opponent_target
    fatigue_category = action.focused_category or ActionCategory.PHYSICAL

    # combat_result is only set on magic-pipeline paths; the combo rider
    # path produces no CombatTechniqueResult.
    combat_result: CombatTechniqueResult | None = None

    # Combo-upgraded actions still run the magic pipeline (the contributor's
    # own technique resolves normally), AND get the combo rider appended.
    # Non-combo actions run the pipeline as before. The only case where the
    # pipeline is skipped: combo-upgraded with no target (defeated opponent).
    run_pipeline = not action.combo_upgrade or target is not None
    if run_pipeline:
        combat_result = _run_combat_technique_pipeline(
            participant, action, technique, fatigue_category, offense_check_fn
        )
        outcome.damage_results.extend(combat_result.damage_results)
        if action.from_entrance:
            _maybe_suggest_entrance_dramatic_moment(participant, combat_result)
        _maybe_produce_insight_for_cast(participant, combat_result, technique)

    # Combo rider: appended in addition to the pipeline result when the
    # action is combo-upgraded and the target is alive.
    if action.combo_upgrade and target is not None:
        _apply_combo_rider(participant, action, target, outcome)

    # Wind-up interception rider (#2637 design 4): a landing hit on a
    # winding-up opponent downgrades its telegraphed attack. No new button —
    # rides the existing damage-landed moment.
    if target is not None:
        _apply_windup_interception_rider(target, outcome, participant)

    # Apply fatigue after action resolves
    apply_fatigue(
        participant.character_sheet,
        fatigue_category,
        technique.anima_cost,
        action.effort_level,
    )

    _record_and_broadcast_pc_action(
        participant=participant,
        action=action,
        technique=technique,
        target=target,
        outcome=outcome,
        combat_result=combat_result,
    )

    # Nemesis/toxic-NPC-bond regard hook (#2039): a PC defeating a notable
    # (persona-backed) NPC opponent records a PC_FOILED_NPC_PLAN regard event.
    # A mook/persona-less opponent's defeat is deliberately a no-op — no
    # NpcRegard row is ever created for it.
    _maybe_record_npc_regard_on_defeat(participant, action, target, outcome)

    return outcome


def _resolve_npc_action_on_target(  # noqa: PLR0913 - per-target resolution needs full context
    target_participant: CombatParticipant,
    *,
    opponent: CombatOpponent,
    npc_action: CombatOpponentAction,
    defense_check_type: CheckType | None,
    defense_check_fn: PerformCheckFn | None,
    conditions: list,
    outcome: ActionOutcome,
    condition_applications: list,
    get_npc_action_interaction: Callable[[], Interaction],
) -> None:
    """Resolve one NPC action against a single target, recording results in place.

    Skips escaped (non-ACTIVE) and dead targets. Applies damage (via a defense
    check when one is configured, else flat threat damage), runs the
    survivability pipeline, and queues any conditions for bulk apply by
    appending to ``outcome`` and ``condition_applications``.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    # A successful escape protects for the rest of the round (#878). The
    # idmapper guarantees this is the same instance _resolve_flee just
    # mutated, so the status write is visible without a re-fetch.
    if target_participant.status != ParticipantStatus.ACTIVE:
        return

    # Damage recipients: any not-dead target is valid. Unconscious / dying
    # PCs still take damage (incapacitation/dying are conditions, not a gate
    # on damage application). Only the dead are excluded.
    if is_dead(target_participant.character_sheet):
        return

    # Survivability pipeline — knockout, death, wound checks.
    # coherence_cache_scope memoizes motif_coherence_bonus per (sheet, resonance)
    # so DR (inside apply_damage_to_participant / resolve_npc_attack) + the three
    # save baselines (inside process_damage_consequences) share one wardrobe walk (#1267).
    from world.magic.services import coherence_cache_scope  # noqa: PLC0415
    from world.vitals.services import process_damage_consequences  # noqa: PLC0415

    with coherence_cache_scope():
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
                int(npc_action.threat_entry.base_damage * npc_action.damage_scale),
                damage_type=npc_action.threat_entry.damage_type,
                source=opponent,
                on_hit_pool=npc_action.threat_entry.on_hit_consequence_pool,
                delivery=npc_action.threat_entry.delivery,
                is_area=npc_action.threat_entry.targeting_mode != TargetingMode.SINGLE,
            )
        outcome.damage_results.append(dmg_result)

        consequence = process_damage_consequences(
            character_sheet=target_participant.character_sheet,
            damage_dealt=dmg_result.damage_dealt,
            damage_type=npc_action.threat_entry.damage_type,
            combat_interaction_factory=get_npc_action_interaction,
            source_character=opponent.objectdb,
        )
    outcome.damage_consequences.append(consequence)

    # Sent Flying trigger (#2638): a sends_flying attack that connects with
    # damage > 0 launches its victim airborne — the plummet-pattern's
    # "in-flight" clone (see the "Sent Flying" function family: _trigger_sent_flying
    # onward, defined above swarm_kills).
    if npc_action.threat_entry.sends_flying and dmg_result.damage_dealt > 0:
        _trigger_sent_flying(target_participant, npc_action, dmg_result.damage_dealt)

    # Nemesis/toxic-NPC-bond regard hook (#2039): a notable (persona-backed)
    # NPC opponent critically harming a PC (death- or permanent-wound-eligible
    # hit) records an NPC_HARMED_PC_INTEREST regard event. A mook/persona-less
    # opponent's hit — or any non-critical hit from a notable NPC — is
    # deliberately a no-op: no NpcRegard row is ever created for it.
    if opponent.persona_id is not None and (
        dmg_result.death_eligible or dmg_result.permanent_wound_eligible
    ):
        from world.npc_services.constants import NpcRegardEventReason  # noqa: PLC0415
        from world.npc_services.regard import (  # noqa: PLC0415
            get_regard_event_config,
            record_npc_regard_event,
        )
        from world.scenes.models import Persona  # noqa: PLC0415

        try:
            pc_persona = target_participant.character_sheet.primary_persona
        except Persona.DoesNotExist:
            pc_persona = None
        if pc_persona is not None:
            cfg = get_regard_event_config()
            record_npc_regard_event(
                holder_persona=opponent.persona,
                target=pc_persona,
                amount=cfg.combat_harm_amount,
                reason=NpcRegardEventReason.NPC_HARMED_PC_INTEREST,
                source_npc_combat_action=npc_action,
            )

    # Collect condition applications for bulk apply
    if dmg_result.damage_dealt > 0 and conditions:
        target_obj = target_participant.character_sheet.character
        condition_applications.extend((target_obj, ct) for ct in conditions)


def _resolve_npc_action_on_opponent_target(
    target_opponent: CombatOpponent,
    *,
    opponent: CombatOpponent,
    npc_action: CombatOpponentAction,
    outcome: ActionOutcome,
) -> None:
    """Resolve one NPC action against a single OPPONENT target (#1584 Task 7b).

    Routes an ALLY summon's attack at an ENEMY opponent. Damage only — the PC
    survivability pipeline (``process_damage_consequences``) and the threat
    entry's ``conditions_applied`` path stay PC-only here;
    ``apply_damage_to_opponent`` already sets ``OpponentStatus.DEFEATED``
    internally. The summoner (``opponent.summoned_by``, a ``CharacterSheet`` or
    ``None``) receives damage/defeat achievement credit; null-safe for
    non-summon attackers.
    """
    # Mirror the participant guard: skip an escaped/defeated (non-ACTIVE) target.
    if target_opponent.status != OpponentStatus.ACTIVE:
        return

    dmg_result = apply_damage_to_opponent(
        target_opponent,
        int(npc_action.threat_entry.base_damage * npc_action.damage_scale),
        damage_type=npc_action.threat_entry.damage_type,
        source_sheet=opponent.summoned_by,
    )
    outcome.damage_results.append(dmg_result)


def _resolve_npc_action(
    opponent: CombatOpponent,
    npc_action: CombatOpponentAction,
    defense_check_type: CheckType | None,
    defense_check_fn: PerformCheckFn | None,
) -> ActionOutcome:
    """Resolve a single NPC's action against its targets.

    Exactly one target relation is populated per action: participant ``targets``
    (the normal PC-facing path — applies damage, knockout/death transitions, and
    threat-entry conditions) or ``opponent_targets`` (an ALLY summon attacking
    ENEMY opponents — damage only; #1584).

    When ``defense_check_type`` is None (production), the defense check type is
    sourced from ``npc_action.threat_entry.defense_check_type`` (#1994). A
    non-None external param (test override) takes precedence.
    """
    # Source from threat entry when no external override is provided (#1994).
    effective_defense_check_type = defense_check_type or npc_action.threat_entry.defense_check_type
    outcome = ActionOutcome(entity_type=ENTITY_TYPE_NPC, entity_label=str(opponent))

    try:
        targets: list[CombatParticipant] = npc_action.cached_targets
    except AttributeError:
        targets = list(npc_action.targets.all())

    try:
        opponent_targets: list[CombatOpponent] = npc_action.cached_opponent_targets
    except AttributeError:
        opponent_targets = list(npc_action.opponent_targets.all())

    # Exactly one relation is populated; use whichever for narration labels.
    label_targets: list = targets or opponent_targets

    # Pre-fetch conditions from the threat entry
    try:
        conditions = npc_action.threat_entry.cached_conditions
    except AttributeError:
        conditions = list(npc_action.threat_entry.conditions_applied.all())

    from world.combat.interaction_services import (  # noqa: PLC0415
        create_npc_action_interaction,
    )

    # Lazy factory: mint the ACTION-mode Interaction only when the first
    # survivability tier actually fires (#864). Memoised so all targets of this
    # NPC action share one row.
    npc_action_label = ", ".join(str(t) for t in label_targets) if label_targets else None
    _npc_interaction_cache: list[Interaction] = []

    def _get_npc_action_interaction() -> Interaction:
        if not _npc_interaction_cache:
            _npc_interaction_cache.append(
                create_npc_action_interaction(
                    opponent_action=npc_action,
                    target_label=npc_action_label,
                )
            )
        return _npc_interaction_cache[0]

    condition_applications: list[tuple[ObjectDB, ConditionTemplate]] = []

    for target_participant in targets:
        _resolve_npc_action_on_target(
            target_participant,
            opponent=opponent,
            npc_action=npc_action,
            defense_check_type=effective_defense_check_type,
            defense_check_fn=defense_check_fn,
            conditions=conditions,
            outcome=outcome,
            condition_applications=condition_applications,
            get_npc_action_interaction=_get_npc_action_interaction,
        )

    # Opponent-target path (#1584): an ALLY summon attacking ENEMY opponents.
    # Damage only — no survivability pipeline, no conditions (out of scope 7b).
    for target_opponent in opponent_targets:
        _resolve_npc_action_on_opponent_target(
            target_opponent,
            opponent=opponent,
            npc_action=npc_action,
            outcome=outcome,
        )

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

    npc_target_label = ", ".join(str(t) for t in label_targets) if label_targets else None
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


def maybe_pause_encounter_for_disconnect(character_sheet: CharacterSheet) -> None:
    """Pause the character's live CombatEncounter, if any, on disconnect (#1899).

    CombatEncounter has no scale exception (it's inherently small-scale —
    PARTY_COMBAT/OPEN_ENCOUNTER/DUEL); every live encounter pauses. Reuses the
    existing is_paused field/semantics unchanged (soft flag; only blocks the
    TIMED-mode auto-resolve sweep, per its existing behavior).
    """
    participant = CombatParticipant.objects.filter(
        character_sheet=character_sheet,
        status=ParticipantStatus.ACTIVE,
        encounter__completed_at__isnull=True,
    ).first()
    if participant is None:
        return
    participant.encounter.is_paused = True
    participant.encounter.save(update_fields=["is_paused"])


def _check_encounter_completion(encounter: CombatEncounter) -> bool:
    """Return True if the encounter should be marked complete.

    Complete when either side is wiped: all opponents defeated, OR every active
    PC is "down" (cannot act — dead or incapacitated). A dying-but-conscious PC
    can still act, so the encounter is not lost while any PC can_act.
    """
    from world.vitals.services import can_act  # noqa: PLC0415

    # Only ENEMY opponents block victory; an ALLY summon staying active must not
    # keep the encounter open (#1584).
    all_opponents_down = not CombatOpponent.objects.filter(
        encounter=encounter,
        status=OpponentStatus.ACTIVE,
        allegiance=CombatAllegiance.ENEMY,
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
    # VICTORY hinges on ENEMY opponents only — an ALLY summon left standing is
    # part of the winning side, not a reason to withhold victory (#1584).
    any_active_opponents = CombatOpponent.objects.filter(
        encounter=encounter,
        status=OpponentStatus.ACTIVE,
        allegiance=CombatAllegiance.ENEMY,
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
    if encounter.status == RoundStatus.COMPLETED:
        msg = f"Encounter {encounter.pk} is already completed."
        raise ValueError(msg)

    encounter.status = RoundStatus.COMPLETED
    encounter.outcome = outcome
    encounter.completed_at = timezone.now()
    encounter.save(update_fields=["status", "outcome", "completed_at"])

    interaction = _broadcast_encounter_outcome(encounter, outcome)

    if outcome != EncounterOutcome.ABANDONED:
        _apply_aftermath_rules(encounter, outcome, interaction)
        _apply_opponent_aftermath_pools(encounter, outcome)
        _increment_completion_counters(encounter, outcome)

    from world.combat.beat_wiring import install_encounter_beat_trigger  # noqa: PLC0415

    install_encounter_beat_trigger(encounter)
    _emit_encounter_completed(encounter, outcome)
    cleanup_completed_encounter(encounter)
    _hand_off_acute_peril_to_scene_round(encounter)


def _hand_off_acute_peril_to_scene_round(encounter: CombatEncounter) -> None:
    """After combat ends, ensure any participant still Bleeding-Out or Plummeting is
    covered by a scene round so the peril keeps ticking (Task 6 — #1466).

    Guards:
    - Only PC participants (``CombatParticipant``), never NPC opponents.
    - Skip characters who are somehow still in another active encounter (paranoid guard).
    """
    from world.areas.positioning.constants import PLUMMETING_CONDITION_NAME  # noqa: PLC0415
    from world.combat.round_context import resolve_combat_round_context  # noqa: PLC0415
    from world.conditions.constants import BLEED_OUT_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.scenes.round_services import ensure_round_for_acute_condition  # noqa: PLC0415

    acute_condition_names = [BLEED_OUT_CONDITION_NAME, PLUMMETING_CONDITION_NAME]

    participants = list(
        CombatParticipant.objects.filter(encounter=encounter).select_related(
            "character_sheet__character"
        )
    )
    for participant in participants:
        sheet = participant.character_sheet
        character = sheet.character
        has_acute = ConditionInstance.objects.filter(
            target=character,
            condition__name__in=acute_condition_names,
        ).exists()
        if not has_acute:
            continue
        # Paranoid guard: skip if the character is already in another active encounter.
        if resolve_combat_round_context(sheet) is not None:
            continue
        ensure_round_for_acute_condition(sheet)


def end_encounter(encounter: CombatEncounter) -> CombatEncounter:
    """GM force-end: completes as ABANDONED (#876 §8)."""
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
        defeated_opponent_labels=[
            o.name
            for o in opponents
            if o.status == OpponentStatus.DEFEATED and o.allegiance == CombatAllegiance.ENEMY
        ],
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
        breakdown = collect_check_modifiers(sheet, rule.check_type, scene=encounter.scene)
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
    """encounters_won / encounters_lost / encounters_fled aggregates (#876 §7).

    A DUEL leaves both PCs as ACTIVE participants at completion (only the loser's
    mirror ``CombatOpponent`` is DEFEATED, never the loser's own participant row),
    so the generic ACTIVE→won rule would credit *both* duelists with a win. For a
    DUEL the win is credited solely to ``encounter.duel_winner`` and the loss to
    the other duelist; an abandoned duel (no ``duel_winner``) credits neither
    (#1182).
    """
    from world.combat.achievement_counters import (  # noqa: PLC0415
        STAT_KEY_ENCOUNTERS_FLED,
        STAT_KEY_ENCOUNTERS_LOST,
        STAT_KEY_ENCOUNTERS_WON,
        increment_combat_counter,
    )

    participants = CombatParticipant.objects.filter(encounter=encounter).select_related(
        "character_sheet"
    )

    if encounter.encounter_type == EncounterType.DUEL:
        winner_sheet_id = encounter.duel_winner_id
        for participant in participants:
            if participant.status == ParticipantStatus.FLED:
                increment_combat_counter(participant.character_sheet, STAT_KEY_ENCOUNTERS_FLED)
            elif winner_sheet_id is None:
                continue  # Abandoned / mutual stop — no victor; credit neither.
            elif participant.character_sheet_id == winner_sheet_id:
                increment_combat_counter(participant.character_sheet, STAT_KEY_ENCOUNTERS_WON)
            else:
                increment_combat_counter(participant.character_sheet, STAT_KEY_ENCOUNTERS_LOST)
        return

    outcome_key = {
        EncounterOutcome.VICTORY: STAT_KEY_ENCOUNTERS_WON,
        EncounterOutcome.DEFEAT: STAT_KEY_ENCOUNTERS_LOST,
    }.get(outcome)

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
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415
    from world.scenes.round_services import (  # noqa: PLC0415
        ChallengeResolutionRequest,
        resolve_challenge_declarations,
    )

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

    requests = [
        ChallengeResolutionRequest(
            character=decl.participant.character_sheet.character,
            challenge_instance=decl.challenge_instance,
            approach=decl.challenge_approach,
            actor_label=str(decl.participant),
        )
        for decl in ordered
    ]
    outcomes = resolve_challenge_declarations(
        requests,
        broadcast=lambda narration: broadcast_action_outcome(
            encounter=encounter, narration=narration
        ),
    )

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


def _try_interpose(
    participant: CombatParticipant,
    pre_payload: DamagePreApplyPayload,
) -> None:
    """Find the first eligible armed INTERPOSE this round and dispatch it.

    Looks for a :class:`~world.combat.models.CombatRoundAction` declaring
    ``INTERPOSE`` for *participant* (or any ally) in the current round, resolves
    the interposer's capability challenge via :func:`dispatch_interpose`, and
    mutates *pre_payload.amount* in place.

    Passes ``select_best_check_rating=True`` (no explicit *approach*) so the
    interposer's better-rated reaction action — Reflexes or the Melee-Defense
    twin, whichever the guardian is actually built for — is picked deterministically
    (#2207; see :func:`~world.mechanics.reactions._select_best_rated_action`).

    **Guard:** no-op when the encounter is not ``RESOLVING`` so that
    non-combat callers of :func:`apply_damage_to_participant` are unaffected.

    Only the *first* eligible interposer is exercised in v1; multiple interposers
    covering the same target is a follow-up.

    **Technique-guardian branch (#2207):** when the declaration carries a
    validated protective technique (``action.focused_action_id`` set — see
    :func:`declare_interpose`), dispatch replaces the mundane capability-reaction
    challenge with :func:`_try_technique_interpose` (the guardian's own cast
    check, anima cost instead of fatigue). The mundane path below is otherwise
    unchanged.
    """
    encounter = participant.encounter
    if encounter.status != RoundStatus.RESOLVING:
        return

    # Bug fix (#2638, discovered while building the sibling sent-flying catch
    # query): Django's `field__in=[x, None]` silently DROPS the None entry —
    # it compiles to a bare `IN (x)`, never `x OR field IS NULL` — so a
    # guard-anyone (`focused_ally_target=None`) declaration could never
    # actually fire here, even though `ally_intercepted_for_me` and
    # `_ensure_interpose_challenges` both correctly treat it as armed cover.
    # Q(...) | Q(...) is required to express the OR NULL branch.
    action = (
        CombatRoundAction.objects.filter(
            Q(focused_ally_target=participant) | Q(focused_ally_target__isnull=True),
            participant__encounter=encounter,
            round_number=encounter.round_number,
            maneuver=CombatManeuver.INTERPOSE,
            participant__status=ParticipantStatus.ACTIVE,
        )
        .select_related("participant__character_sheet__character")
        .first()
    )
    if action is None:
        return

    # Skip self-interpose: the interposer cannot block damage aimed at themselves.
    if action.participant_id == participant.pk:
        return

    protected = participant.character_sheet.character
    _dispatch_interpose_action(action, protected, pre_payload)


def _try_interpose_for_opponent(
    opponent: CombatOpponent,
    pre_payload: DamagePreApplyPayload,
) -> None:
    """Guardian-shields-a-summon variant of :func:`_try_interpose` (#2207).

    Extends interpose protection to ALLY-allegiance ``CombatOpponent`` wards —
    player summons/companion NPCs fighting on the party's side — so a declared
    guardian can shield them the same way they can shield a PC. No-op when
    *opponent* is not ``allegiance=ALLY`` (an ENEMY opponent is never a ward)
    or when the encounter is not ``RESOLVING`` (mirrors :func:`_try_interpose`).

    **ANY-ALLY only:** ``CombatRoundAction.focused_ally_target`` FKs
    ``CombatParticipant``, so a ``CombatOpponent`` can never be named as a
    *specific* ward — only an armed ``focused_ally_target IS NULL`` (any-ally)
    declaration can pick it up. Named-ally guarding of a summon is a follow-up
    once ``focused_ally_target`` (or a sibling field) can point at an opponent.
    There is no self-interpose check here (unlike :func:`_try_interpose`): the
    interposer is always a ``CombatParticipant`` and the ward is always a
    ``CombatOpponent``, so the two can never be the same row.
    """
    if opponent.allegiance != CombatAllegiance.ALLY:
        return

    encounter = opponent.encounter
    if encounter.status != RoundStatus.RESOLVING:
        return

    action = (
        CombatRoundAction.objects.filter(
            participant__encounter=encounter,
            round_number=encounter.round_number,
            maneuver=CombatManeuver.INTERPOSE,
            focused_ally_target__isnull=True,
            participant__status=ParticipantStatus.ACTIVE,
        )
        .select_related("participant__character_sheet__character")
        .first()
    )
    if action is None:
        return

    _dispatch_interpose_action(action, pre_payload.target, pre_payload)


def _dispatch_interpose_action(
    action: CombatRoundAction,
    protected: ObjectDB,  # noqa: OBJECTDB_PARAM
    pre_payload: DamagePreApplyPayload,
) -> None:
    """Resolve an armed INTERPOSE action against *protected* and mutate pre_payload.

    Shared tail for both ward types (#2207): a ``CombatParticipant`` ward
    (:func:`_try_interpose`) and an ALLY-allegiance ``CombatOpponent``/summon
    ward (:func:`_try_interpose_for_opponent`). Handles the technique-vs-mundane
    branch, bond bonus, and interposer fatigue charge identically for both —
    extracted so the two callers don't duplicate this body (#2207).

    **Reaction economy (#2639), shared fire seam per F-10c:** declines with
    the same "did not fire" no-op shape (no dispatch, no fatigue, pre_payload
    untouched) when either budget is exhausted — the interposer has already
    spent their ``REACTIONS_PER_ROUND`` reaction this round, or this specific
    payload has already been answered by ``ABSORPTION_CAP_PER_MOMENT``
    interceptors. Both counters increment together on an actual attempt
    (readiness is free; only firing spends the budget), regardless of whether
    the guardian's own roll then succeeds.
    """
    participant = action.participant
    if participant.reactions_used >= REACTIONS_PER_ROUND:
        return
    if pre_payload.answers_consumed >= ABSORPTION_CAP_PER_MOMENT:
        return

    participant.reactions_used += 1
    participant.save(update_fields=["reactions_used"])
    pre_payload.answers_consumed += 1

    interposer = action.participant.character_sheet.character

    # Bond combat bonus (#2021): relationship-scaled protection.
    from world.relationships.services import bond_bonus  # noqa: PLC0415

    modifiers = bond_bonus(interposer, protected)

    if action.focused_action_id is not None:
        _try_technique_interpose(
            action,
            interposer,
            protected,
            pre_payload,
            extra_modifiers=modifiers,
        )
        return

    result = dispatch_interpose(
        interposer,
        protected,
        pre_payload,
        approach=None,
        extra_modifiers=modifiers,
        select_best_check_rating=True,
    )
    if result is not None:
        # Charge fatigue to the interposer ONLY on fire (readiness is free).
        # Mirror _resolve_pc_action: apply_fatigue(sheet, category, base_cost, effort).
        fatigue_category = action.focused_category or ActionCategory.PHYSICAL
        apply_fatigue(
            action.participant.character_sheet,
            fatigue_category,
            INTERPOSE_BASE_FATIGUE_COST,
            action.effort_level,
        )


def _try_technique_interpose(
    action: CombatRoundAction,
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
    protected: ObjectDB,  # noqa: OBJECTDB_PARAM
    pre_payload: DamagePreApplyPayload,
    *,
    extra_modifiers: int = 0,
) -> None:
    """Resolve a technique-guardian's protective reactive-trigger technique (#2207).

    Runs when ``action.focused_action_id`` is set — the guardian declared a
    known protective technique (``declare_interpose(technique=...)``) instead of
    a plain mundane interpose. Diverges from :func:`dispatch_interpose` in three
    ways:

    1. **Affordability first.** Cost is the matched protective
       ``ConditionTemplate.reactive_anima_cost`` (resolved via
       :func:`~world.magic.services.targeting.protective_condition_and_flavor` —
       the same traversal :func:`~world.magic.services.targeting.protective_flavor`
       walks at declaration time, first protective-flavored template wins). Can't
       pay -> the reaction fizzles silently: NO roll, NO fatigue, NO anima
       charged, and damage proceeds unchanged to ``_try_companion_defend`` as
       today.
    2. **The roll is the guardian's own cast check**
       (:func:`~world.magic.services.anima.resolve_cast_check_type`), rolled
       against the same authored difficulty as the mundane Interpose challenge
       (:data:`~world.combat.interpose_content.INTERPOSE_CHALLENGE_NAME`'s
       ``ChallengeTemplate.severity``) — a technique guardian's protection is
       spellcasting, not martial reflex, so it never touches
       :func:`dispatch_capability_reaction`.
    3. **Cost is anima, not fatigue.** On fire (any non-fizzle resolution) the
       guardian's anima is debited directly (mirrors
       :func:`~world.magic.services.effect_handlers._try_spend_reactive`'s debit
       pattern, minus the ``ConditionInstance`` machinery — the guardian is
       casting live, not carrying a passive buff). No
       ``INTERPOSE_BASE_FATIGUE_COST`` is charged on this path.

    Grading reuses :func:`_grade_interpose_damage` — the SAME clean/partial/fail
    banding (including SHIELD divisor widening) the mundane path uses via
    :func:`apply_interpose_outcome`, so a technique guardian and a mundane
    guardian resolve identically once the check lands.

    **BLINK flavor, clean success only:** relocates *protected* (the ward) to
    *interposer*'s own current position — "you're with me now," out of harm's
    way — via :func:`~world.areas.positioning.services.force_move_to_position`
    (the same unchecked-move primitive
    :func:`~world.magic.services.effect_handlers.blink_dodge` uses). Destination
    is the guardian's own position because this branch predates #2206: once
    ``CombatRoundAction.cast_destination`` lands, queue-time reconciliation
    should prefer that declared destination over the guardian's own position.
    No-op (damage still zeroed) if the guardian isn't currently placed anywhere.

    **REDIRECT flavor (#2210):** after grading, ``saved = amount_before -
    pre_payload.amount`` (whatever the block prevented — full on a clean
    block, half on a partial, zero on a failure) is sent to the declaration's
    destination (``CombatRoundAction.redirect_opponent_target`` /
    ``redirect_object_target`` — see :func:`_resolve_technique_redirect`).
    """
    from world.combat.interpose_content import INTERPOSE_CHALLENGE_NAME  # noqa: PLC0415
    from world.magic.models.anima import CharacterAnima  # noqa: PLC0415
    from world.magic.services.anima import resolve_cast_check_type  # noqa: PLC0415
    from world.magic.services.targeting import (  # noqa: PLC0415
        PROTECTIVE_FLAVOR_BLINK,
        PROTECTIVE_FLAVOR_REDIRECT,
        protective_condition_and_flavor,
    )
    from world.mechanics.models import ChallengeTemplate  # noqa: PLC0415

    technique = action.focused_action

    resolved = protective_condition_and_flavor(technique)
    if resolved is None:
        # declare_interpose already validated this at declaration time; fail
        # safe (damage proceeds unchanged) rather than crash if authored
        # content changed mid-encounter.
        return
    condition_template, flavor = resolved

    # Affordability first (mirrors _try_spend_reactive's cost<=0 free-fire rule,
    # world/magic/services/effect_handlers.py): a free-cost protective technique
    # never needs a CharacterAnima row to fire.
    cost = condition_template.reactive_anima_cost
    anima = None
    if cost > 0:
        anima = CharacterAnima.objects.filter(character=interposer).first()
        if anima is None or anima.current < cost:
            return  # Fizzle: unaffordable — no roll, no cost, damage proceeds.

    severity_template = ChallengeTemplate.objects.filter(name=INTERPOSE_CHALLENGE_NAME).first()
    if severity_template is None:
        # Unseeded content (mirrors _ensure_interpose_challenges' warn-and-skip
        # for the mundane path): fail safe like the resolved-is-None branch
        # above — no roll, no cost, damage proceeds unchanged.
        return
    severity = severity_template.severity
    check_type = resolve_cast_check_type(interposer, technique.action_template)
    if check_type is None:
        # Unprovisioned caster + template-less technique (clash.py guards the
        # same pairing) — fail safe like the resolved-is-None branch above:
        # no roll, no cost, damage proceeds to the next protection layer.
        return
    # #2536 Task 5 review fix: thread the live round context — action.participant
    # is already dereferenced elsewhere in this function (current_position below),
    # so the plumbing a CHECK_BONUS perk needs is trivially available; skipping it
    # would silently strand a future perk scoped to the guardian's protective
    # technique CheckType. No natural offense `target` exists on a reactive
    # protective roll (there is no opposing actor being checked against), so
    # target stays None — only holder/subject/resolution-keyed situations apply.
    from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
    from world.covenants.perks.context import SituationContext  # noqa: PLC0415

    situation_ctx = SituationContext(
        holder=action.participant.character_sheet,
        subject=action.participant.character_sheet,
        target=None,
        resolution=CombatRoundContext(action.participant),
    )
    check_result = perform_check(
        interposer,
        check_type,
        target_difficulty=severity,
        extra_modifiers=extra_modifiers,
        situation_ctx=situation_ctx,
    )

    # Debit on fire (any non-fizzle resolution) — anima, not fatigue.
    if cost > 0:
        anima.current -= cost
        anima.save(update_fields=["current"])

    amount_before = pre_payload.amount
    is_clean_block = _grade_interpose_damage(
        pre_payload, check_result.success_level, interposer=interposer
    )

    if is_clean_block and flavor == PROTECTIVE_FLAVOR_BLINK:
        from world.areas.positioning.services import force_move_to_position  # noqa: PLC0415

        dest = action.participant.current_position
        if dest is not None:
            force_move_to_position(protected, dest)

    if flavor == PROTECTIVE_FLAVOR_REDIRECT:
        saved = amount_before - pre_payload.amount
        _resolve_technique_redirect(action, interposer, saved, damage_type=pre_payload.damage_type)


def _resolve_technique_redirect(
    action: CombatRoundAction,
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
    saved: int,
    *,
    damage_type: DamageType | None,
) -> None:
    """Resolve a REDIRECT-flavor guardian's saved damage into its destination (#2210).

    ``saved`` is whatever :func:`_grade_interpose_damage` prevented from landing on
    the ward — full amount on a clean block, half on a partial, zero on a failure.
    ``saved <= 0`` means nothing redirects (a failed block has nothing to send
    anywhere). Otherwise dispatches per the declaration
    (``CombatRoundAction.redirect_opponent_target`` / ``redirect_object_target``,
    set by :func:`declare_interpose`); both null (or a destination that's no
    longer valid at resolution time — the target defeated, the object moved or
    already consumed) degrades to "away," the universal fallback.
    """
    if saved <= 0:
        return

    encounter = action.participant.encounter
    opponent = action.redirect_opponent_target
    obj = action.redirect_object_target

    if opponent is not None:
        if opponent.status == OpponentStatus.ACTIVE:
            _redirect_to_opponent(encounter, interposer, opponent, saved, damage_type=damage_type)
        else:
            _redirect_away(encounter, interposer)
        return

    if obj is not None:
        from world.mechanics.services import volatile_object_property  # noqa: PLC0415

        obj_property = volatile_object_property(obj)
        if obj.db_location_id == encounter.room_id and obj_property is not None:
            _redirect_to_object(encounter, interposer, obj, obj_property)
        else:
            _redirect_away(encounter, interposer)
        return

    _redirect_away(encounter, interposer)


def _redirect_away(
    encounter: CombatEncounter,
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
) -> None:
    """Broadcast the "away" redirect outcome — a silent deflection, no target hit."""
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    narration = f"{interposer.db_key} turns the blow aside — it goes wide, harming no one."
    broadcast_action_outcome(encounter=encounter, narration=narration)


def _redirect_to_opponent(
    encounter: CombatEncounter,
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
    opponent: CombatOpponent,
    saved: int,
    *,
    damage_type: DamageType | None,
) -> None:
    """Apply the saved damage to the declared chosen-enemy opponent and broadcast it."""
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    apply_damage_to_opponent(opponent, saved, bypass_pre_apply=True, damage_type=damage_type)
    narration = f"{interposer.db_key} hurls the blow back — it slams into {opponent.name}!"
    broadcast_action_outcome(encounter=encounter, narration=narration)


def _redirect_to_object(
    encounter: CombatEncounter,
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
    obj: ObjectDB,  # noqa: OBJECTDB_PARAM
    obj_property: ObjectProperty,
) -> None:
    """Detonate the declared volatile object: fire its pool, consume it, broadcast it.

    Position-anchored only — an object with no ``Position`` (shouldn't happen for
    a volatile object placed in a room with staged positions, but a defensive
    guard) degrades to "away" rather than firing at "everyone in the room."
    """
    from world.areas.positioning.services import position_of  # noqa: PLC0415
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415
    from world.room_features.trap_services import fire_pool_at_characters  # noqa: PLC0415

    position = position_of(obj)
    if position is None:
        _redirect_away(encounter, interposer)
        return

    characters = _combatants_at_position(encounter, position)
    fire_pool_at_characters(
        obj_property.property.detonation.consequence_pool,
        characters,
        source_character=interposer,
    )
    obj_property.delete()

    narration = f"{interposer.db_key} hurls the blow into {obj.db_key} — it detonates!"
    broadcast_action_outcome(encounter=encounter, narration=narration)


def _combatants_at_position(
    encounter: CombatEncounter,
    position: Position,
) -> list[ObjectDB]:  # noqa: OBJECTDB_PARAM
    """Every ACTIVE participant's character + ACTIVE opponent's objectdb at *position*.

    Single query against ``position.occupants`` (the ``ObjectPosition`` reverse
    relation) rather than calling ``current_position`` per combatant, to avoid a
    query-in-a-loop over the encounter's roster.
    """
    occupant_ids = set(position.occupants.values_list("objectdb_id", flat=True))

    characters: list[ObjectDB] = [
        p.character_sheet.character
        for p in CombatParticipant.objects.filter(
            encounter=encounter, status=ParticipantStatus.ACTIVE
        ).select_related("character_sheet__character")
        if p.character_sheet.character_id in occupant_ids
    ]
    characters.extend(
        opp.objectdb
        for opp in CombatOpponent.objects.filter(
            encounter=encounter, status=OpponentStatus.ACTIVE
        ).select_related("objectdb")
        if opp.objectdb_id is not None and opp.objectdb_id in occupant_ids
    )
    return characters


def _try_companion_defend(
    participant: CombatParticipant,
    pre_payload: DamagePreApplyPayload,
) -> None:
    """Check for a companion ordered to DEFEND_ALLY for this participant (#1921).

    If found, redirect the damage to the companion's CombatOpponent via
    ``apply_damage_to_opponent`` (which handles soak, resistance, and defeat).
    The companion's soak applies. If the companion is defeated, overflow
    damage passes through to the original target.

    **Guard:** no-op when the encounter is not ``RESOLVING`` so that
    non-combat callers of :func:`apply_damage_to_participant` are unaffected.
    """
    from world.companions.constants import CompanionOrderKind  # noqa: PLC0415
    from world.companions.models import CompanionOrder  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.RESOLVING:
        return

    order = (
        CompanionOrder.objects.filter(
            defending_participant=participant,
            encounter=encounter,
            round_number=encounter.round_number,
            order_kind=CompanionOrderKind.DEFEND_ALLY,
        )
        .select_related("companion")
        .first()
    )
    if order is None:
        return

    # Find the companion's materialized CombatOpponent
    companion_opponent = CombatOpponent.objects.filter(
        summoned_by=order.companion.owner,
        encounter=encounter,
        status=OpponentStatus.ACTIVE,
    ).first()
    if companion_opponent is None:
        return

    # Redirect damage to the companion. skip_guardian_shield=True: the
    # guardian already had a chance to interpose for `participant` above via
    # _try_interpose (same blow) — without this, the redirect re-enters
    # _resolve_opponent_pre_apply -> _try_guardian_shield_opponent and would
    # charge that guardian's interpose fatigue/anima a second time for one
    # hit (#2207 review finding I1). The companion's own DAMAGE_PRE_APPLY
    # trigger band still runs.
    apply_damage_to_opponent(
        companion_opponent,
        pre_payload.amount,
        damage_type=pre_payload.damage_type,
        skip_guardian_shield=True,
    )

    # If companion survived, zero out the damage to the ally
    if companion_opponent.status == OpponentStatus.ACTIVE:
        pre_payload.amount = 0
    else:
        # Companion defeated; overflow damage goes to the ally
        pre_payload.amount = max(0, pre_payload.amount - companion_opponent.max_health)


def _fire_on_hit_pool(
    character: Character,
    source: object | None,
    pool: ConsequencePool,
) -> None:
    """Fire an attack's on-hit consequence pool (e.g. knockback) against the
    defender, then re-check the defender's landing position for hazards.

    Deterministic — no roll — since the attack's own hit already landed.
    ``source`` is expected to be the attacking ``CombatOpponent`` (the only
    caller wiring ``on_hit_pool`` today is ``resolve_npc_attack``, which
    passes ``source=opponent_action.opponent``); if it isn't a
    ``CombatOpponent`` with a placed ``objectdb``, there's no attacker
    Position to compute "away from actor" against, so this is a no-op.
    """
    from world.areas.positioning.services import position_of  # noqa: PLC0415
    from world.checks.consequence_resolution import apply_pool_deterministically  # noqa: PLC0415
    from world.checks.types import ResolutionContext  # noqa: PLC0415
    from world.room_features.trap_services import check_traps_at_position  # noqa: PLC0415

    if not isinstance(source, CombatOpponent) or source.objectdb_id is None:
        return

    apply_pool_deterministically(
        pool=pool,
        context=ResolutionContext(character=source.objectdb, target=character),
    )

    landing_position = position_of(character)
    if landing_position is not None:
        check_traps_at_position(character, landing_position)


def _bind_interpose_challenges_any_ally(
    template: object,
    room: object,
    interposer_participant_id: int,
    active_participants_by_id: dict[int, CombatParticipant],
    active_ally_opponent_objectdbs: list[ObjectDB],
) -> None:
    """Bind a ChallengeInstance to every active participant and ALLY opponent.

    Every active participant except the interposer, plus every ALLY-allegiance
    ``CombatOpponent``'s objectdb (player summons/companion NPCs, #2207) — so a
    mundane guardian's :func:`dispatch_capability_reaction` finds a bound
    challenge instance when shielding a summon via the ANY-ALLY path. Note: this
    is the ONLY path that can bind a summon-ward — ``focused_ally_target`` FKs
    ``CombatParticipant``, so a summon can never be named as a *specific* ward
    (named-ally guarding of a summon is a follow-up).
    """
    from world.mechanics.models import ChallengeInstance  # noqa: PLC0415

    for part_id, part in active_participants_by_id.items():
        if part_id == interposer_participant_id:
            continue
        ally_char = part.character_sheet.character
        ChallengeInstance.objects.get_or_create(
            template=template,
            target_object=ally_char,
            is_active=True,
            defaults={"location": room, "is_revealed": True},
        )

    for ally_objectdb in active_ally_opponent_objectdbs:
        ChallengeInstance.objects.get_or_create(
            template=template,
            target_object=ally_objectdb,
            is_active=True,
            defaults={"location": room, "is_revealed": True},
        )


def _ensure_interpose_challenges(
    encounter: CombatEncounter,
    pc_actions: dict[int, CombatRoundAction],
) -> None:
    """Round pre-pass: bind an Interpose ChallengeInstance to each protected ally.

    For every armed INTERPOSE ``CombatRoundAction`` this round, idempotently
    ``get_or_create`` an active+revealed ``ChallengeInstance`` from the seeded
    Interpose ``ChallengeTemplate`` bound to each protected ally's character
    ObjectDB (``target_object``), so ``get_available_actions(interposer, room)``
    can surface the approach.

    - Specific-ally path (``focused_ally_target`` set): binds to that ally's character.
    - Any-ally path (``focused_ally_target=None``): binds to every ACTIVE participant
      in this encounter except the interposer, plus every ACTIVE ALLY-allegiance
      ``CombatOpponent``'s objectdb (a summon/companion NPC, #2207) — the only path
      that can bind a summon-ward, since ``focused_ally_target`` FKs
      ``CombatParticipant`` and so cannot name a specific opponent.

    Idempotent: ``get_or_create`` on (template, target_object, is_active=True) ensures
    no duplicates when called multiple times in the same round.

    No queries in loops: the active-ally list is fetched once per any-ally action;
    the template is fetched once before the loop.
    """
    from world.mechanics.models import ChallengeInstance, ChallengeTemplate  # noqa: PLC0415

    # Collect armed interpose actions for this round.
    interpose_actions = [
        action
        for action in pc_actions.values()
        if action.maneuver == CombatManeuver.INTERPOSE and action.is_ready
    ]
    if not interpose_actions:
        return

    try:
        template = ChallengeTemplate.objects.get(name="Interpose")
    except ChallengeTemplate.DoesNotExist:
        logger.warning(
            "Interpose ChallengeTemplate not seeded; skipping challenge binding for encounter %s.",
            encounter.pk,
        )
        return

    room = encounter.room

    # Fetch all active allies once (needed for the any-ally path).
    # select_related prevents N+1 when accessing .character_sheet.character below.
    active_participants_by_id: dict[int, CombatParticipant] | None = None
    # Fetch active ALLY-allegiance opponents (summons/companion NPCs) once too,
    # for the same any-ally path (#2207).
    active_ally_opponent_objectdbs: list[ObjectDB] | None = None

    for action in interpose_actions:
        interposer_participant_id = action.participant_id

        if action.focused_ally_target_id is not None:
            # Specific-ally path: bind to the declared ally's character.
            ally_char = action.focused_ally_target.character_sheet.character
            ChallengeInstance.objects.get_or_create(
                template=template,
                target_object=ally_char,
                is_active=True,
                defaults={"location": room, "is_revealed": True},
            )
        else:
            # Any-ally path: bind to every active participant except the interposer,
            # plus every active ALLY-allegiance opponent (summon/companion NPC, #2207).
            if active_participants_by_id is None:
                active_participants_by_id = {
                    p.pk: p
                    for p in CombatParticipant.objects.filter(
                        encounter=encounter,
                        status=ParticipantStatus.ACTIVE,
                    ).select_related("character_sheet__character")
                }
            if active_ally_opponent_objectdbs is None:
                active_ally_opponent_objectdbs = [
                    opp.objectdb
                    for opp in CombatOpponent.objects.filter(
                        encounter=encounter,
                        status=OpponentStatus.ACTIVE,
                        allegiance=CombatAllegiance.ALLY,
                    ).select_related("objectdb")
                    if opp.objectdb is not None
                ]
            _bind_interpose_challenges_any_ally(
                template,
                room,
                interposer_participant_id,
                active_participants_by_id,
                active_ally_opponent_objectdbs,
            )


def _grade_interpose_damage(
    pre_payload: DamagePreApplyPayload,
    success_level: int,
    *,
    interposer: object | None = None,
    force_clean: bool = False,
) -> bool:
    """Shared clean/partial/fail damage banding for BOTH interpose paths (#2207).

    Extracted from :func:`apply_interpose_outcome` (the mundane
    capability-reaction path) so :func:`_try_technique_interpose` (a technique
    guardian's own cast-check resolution) grades identically without
    duplicating the covenant-role-scaling partial-block math:

    - **clean block** (``force_clean`` or ``success_level > 0``): the blow is
      fully turned aside — ``pre_payload.amount = 0``.
    - **partial** (``success_level == 0``, not forced-clean): the interposer
      softens but does not stop the blow — ``pre_payload.amount //= 2``. An
      interposer engaged in a role with a ``combat_interpose`` scaling row
      scales this reduction by their COVENANT_ROLE thread level (#2022,
      #2529): the deeper the vow, the more damage the partial block absorbs.
    - **failure** (``success_level < 0``): the interpose fails — no change.

    ``force_clean`` lets a caller fold in a resolution-type override (the
    mundane path's ``ChallengeResolutionResult.resolution_type == DESTROY``)
    without leaking that concept into this shared helper's contract.

    Returns ``True`` when this graded as a clean block — the technique path
    uses this to gate BLINK ward relocation (clean success only).
    """
    is_clean_block = force_clean or success_level > 0

    if is_clean_block:
        pre_payload.amount = 0
        return True

    if success_level == 0:
        # #2022/#2529: covenant-role scaling — a deeper vow blocks more damage
        # on a partial block. The bonus reduces the remaining damage further.
        divisor = 2
        if interposer is not None:
            from world.covenants.services import (  # noqa: PLC0415
                covenant_role_action_scaling_bonus,
            )

            bonus = covenant_role_action_scaling_bonus(interposer, "combat_interpose")
            if bonus > 0:
                # Scale: partial block reduces to amount / (2 + bonus).
                # A bonus of 1.0 (a deep SHIELD vow) makes the divisor 3,
                # blocking 67% instead of 50%.
                divisor = int(2 + bonus)
        pre_payload.amount //= divisor
        return False

    # Failure (success_level < 0) — the blow continues at full damage.
    return False


def apply_interpose_outcome(
    pre_payload: DamagePreApplyPayload,
    result: ChallengeResolutionResult,
    *,
    interposer: object | None = None,
) -> None:
    """Map a graded interpose resolution onto *pre_payload*.

    Mirrors :func:`~world.areas.positioning.plummet.resolve_catch`'s graded
    branches but acts on the incoming damage amount rather than plummet state.
    Delegates the clean/partial/fail banding to :func:`_grade_interpose_damage`
    (shared with the technique-guardian path, #2207) — this wrapper's only job
    is converting a ``ChallengeResolutionResult`` into the ``(success_level,
    force_clean)`` pair that helper expects: ``resolution_type == DESTROY``
    forces a clean block even at ``success_level <= 0`` (a capability-authored
    instant stop).
    """
    from world.mechanics.constants import ResolutionType  # noqa: PLC0415

    check_result = result.check_result
    success_level = check_result.success_level if check_result is not None else 0
    force_clean = result.resolution_type == ResolutionType.DESTROY

    _grade_interpose_damage(
        pre_payload, success_level, interposer=interposer, force_clean=force_clean
    )


def dispatch_interpose(  # noqa: PLR0913 - select_best_check_rating extends existing signature
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
    protected: ObjectDB,  # noqa: OBJECTDB_PARAM
    pre_payload: DamagePreApplyPayload,
    *,
    approach: str | None,
    extra_modifiers: int = 0,
    select_best_check_rating: bool = False,
) -> ChallengeResolutionResult | None:
    """Resolve *interposer*'s interpose attempt and apply the graded outcome.

    Thin wrapper over :func:`~world.mechanics.reactions.dispatch_capability_reaction`:
    looks up the active Interpose :class:`~world.mechanics.models.ChallengeInstance`
    bound to *protected*, resolves it through *interposer*'s capabilities, and
    calls :func:`apply_interpose_outcome` to mutate *pre_payload* in place.

    *select_best_check_rating* (#2207) opts into the best-of-check reaction-action
    selection (Reflexes vs. the Melee-Defense twin) when *approach* is ``None`` —
    passed ``True`` by :func:`_try_interpose` (the combat damage path). Default
    ``False`` preserves the plain first-match behavior for the scene-cover caller
    (``world.scenes.sudden_harm``), which passes ``approach=None`` unchanged.

    Returns the :class:`~world.mechanics.types.ChallengeResolutionResult`, or
    ``None`` when no active Interpose challenge is bound to *protected* or
    *interposer* has no qualifying approach.
    """
    import functools  # noqa: PLC0415

    from world.combat.interpose_content import INTERPOSE_CHALLENGE_NAME  # noqa: PLC0415
    from world.mechanics.reactions import dispatch_capability_reaction  # noqa: PLC0415

    return dispatch_capability_reaction(
        interposer,
        protected,
        challenge_name=INTERPOSE_CHALLENGE_NAME,
        approach=approach,
        error_msg=(
            f"No interpose approach is available to {interposer!r} "
            f"for protected target {protected!r}."
        ),
        outcome_fn=functools.partial(apply_interpose_outcome, pre_payload, interposer=interposer),
        select_best_check_rating=select_best_check_rating,
        extra_modifiers=extra_modifiers,
    )


def _ensure_succor_challenges(
    encounter: CombatEncounter,
    pc_actions: dict[int, CombatRoundAction],
) -> None:
    """Round pre-pass: bind a Succor ChallengeInstance to each protected ally.

    Mirrors _ensure_interpose_challenges but Succor always names a specific ally
    (no "any ally" path — see declare_succor's docstring).
    """
    from world.mechanics.models import ChallengeInstance, ChallengeTemplate  # noqa: PLC0415

    succor_actions = [
        action
        for action in pc_actions.values()
        if action.maneuver == CombatManeuver.SUCCOR and action.is_ready
    ]
    if not succor_actions:
        return

    from world.combat.succor_content import SUCCOR_CHALLENGE_NAME  # noqa: PLC0415

    try:
        template = ChallengeTemplate.objects.get(name=SUCCOR_CHALLENGE_NAME)
    except ChallengeTemplate.DoesNotExist:
        logger.warning(
            "Succor ChallengeTemplate not seeded; skipping challenge binding for encounter %s.",
            encounter.pk,
        )
        return

    room = encounter.room
    for action in succor_actions:
        ally_char = action.focused_ally_target.character_sheet.character
        ChallengeInstance.objects.get_or_create(
            template=template,
            target_object=ally_char,
            is_active=True,
            defaults={"location": room, "is_revealed": True},
        )


def _ensure_reactive_challenges(
    encounter: CombatEncounter,
    pc_actions: dict[int, CombatRoundAction],
) -> None:
    """Round pre-pass: bind both Interpose and Succor challenge instances.

    A single call site for ``resolve_round`` (#1273, #1744) — keeps the two
    independent reactive-challenge binders (blow vs. hazard) from adding a
    second statement to an already-large function.
    """
    _ensure_interpose_challenges(encounter, pc_actions)
    _ensure_succor_challenges(encounter, pc_actions)


def dispatch_succor(
    succorer: ObjectDB,  # noqa: OBJECTDB_PARAM
    protected: ObjectDB,  # noqa: OBJECTDB_PARAM
    *,
    approach: str | None,
    extra_modifiers: int = 0,
) -> float:
    """Resolve *succorer*'s Succor attempt against *protected* and return the multiplier.

    Thin wrapper over dispatch_capability_reaction, mirroring dispatch_interpose.
    Returns 1.0 (no cover) when no active Succor challenge is bound to *protected*.
    """
    from world.combat.succor_content import SUCCOR_CHALLENGE_NAME  # noqa: PLC0415
    from world.mechanics.reactions import dispatch_capability_reaction  # noqa: PLC0415
    from world.mechanics.succor_shared import apply_succor_outcome  # noqa: PLC0415

    outcome = {"multiplier": 1.0}

    def _capture(result: ChallengeResolutionResult) -> None:
        outcome["multiplier"] = apply_succor_outcome(result)

    result = dispatch_capability_reaction(
        succorer,
        protected,
        challenge_name=SUCCOR_CHALLENGE_NAME,
        approach=approach,
        error_msg=(
            f"No succor approach is available to {succorer!r} for protected target {protected!r}."
        ),
        outcome_fn=_capture,
        extra_modifiers=extra_modifiers,
    )
    if result is None:
        return 1.0
    return outcome["multiplier"]


def _get_anima(character: ObjectDB) -> CharacterAnima | None:  # noqa: OBJECTDB_PARAM
    """Return the CharacterAnima row for *character*, or None if absent.

    Uses the ``anima`` reverse OneToOneField relation set by
    ``CharacterAnima.character`` (``related_name="anima"``). Mirrors the
    accessor used by ``CombatParticipant.available_strain``.

    Returns None when no CharacterAnima row exists (defensive; characters
    without an anima pool cannot sustain reactive conditions).
    """
    from world.magic.models.anima import CharacterAnima  # noqa: PLC0415

    try:
        return CharacterAnima.objects.get(character=character)
    except CharacterAnima.DoesNotExist:
        return None


def _fire_round_start(enc: CombatEncounter, round_number: int) -> list[AvailableCombo]:
    """Emit COMBAT_ROUND_STARTING, drain upkeep, detect combos.

    Called once at the top of ``resolve_round`` after the DECLARING→RESOLVING
    transition.  Bundles three sequential steps so the caller contributes a
    single statement toward the ``PLR0915`` limit.
    """
    emit_event(
        EventName.COMBAT_ROUND_STARTING,
        CombatRoundStartingPayload(
            encounter_id=enc.pk,
            round_number=round_number,
        ),
        location=enc.room,
    )
    drain_reactive_upkeep(enc)
    return detect_available_combos(enc, round_number)


def _debit_ally_paid_upkeep(inst: ConditionInstance, cost: int) -> None:
    """Debit a condition's upkeep from its ally ``source_character`` payer.

    The payer is the condition's ``source_character`` — distinct from the
    bearer. If the payer cannot pay in full, the condition lapses (its
    ``ConditionInstance`` row is deleted and any ``Trigger`` rows on it
    cascade). Otherwise the payer's anima pool is debited immediately.
    """
    payer_anima = _get_anima(inst.source_character)
    if payer_anima is None or payer_anima.current < cost:
        inst.delete()  # lapse — Trigger rows cascade via source_condition FK
    else:
        payer_anima.current -= cost
        payer_anima.save(update_fields=["current"])


def drain_reactive_upkeep(encounter: CombatEncounter) -> None:
    """Debit per-round upkeep from each active participant's sustained conditions.

    For each ACTIVE participant, for each active (not suppressed, not resolved)
    condition with ``upkeep_anima_per_round > 0``: spend that anima from the
    condition's payer's ``CharacterAnima`` pool. If the payer cannot pay in
    full, the condition lapses — its ``ConditionInstance`` row is deleted and
    any ``Trigger`` rows on it cascade.

    Payer rule (#2208): ``source_character`` pays when set — an ally ward
    strains its caster, never its bearer. Self-cast wards are unchanged
    (source == bearer). Only looking up a separate ``CharacterAnima`` when
    ``source_character_id`` differs from the bearer's keeps the common
    self-ward path on the single-query-per-participant code path below.

    Participants without a ``CharacterAnima`` row are skipped entirely — including
    any caster-paid wards they bear (ADR-0118 edge: an anima-less bearer's ally
    ward gets free upkeep; acceptable because player characters always have an
    anima row).

    Anima is written at most once per participant (after the inner loop) so that
    a round with N self-sustained conditions produces a single UPDATE rather
    than N; ally-sourced conditions debit their payer's pool immediately since
    that payer is not necessarily among the participants being iterated.
    """
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    parts = CombatParticipant.objects.filter(
        encounter=encounter, status=ParticipantStatus.ACTIVE
    ).select_related("character_sheet__character")
    for part in parts:
        char = part.character_sheet.character
        anima = _get_anima(char)
        if anima is None:
            continue
        instances = ConditionInstance.objects.filter(
            target=char,
            is_suppressed=False,
            resolved_at__isnull=True,
            condition__upkeep_anima_per_round__gt=0,
        ).select_related("condition")
        remaining = anima.current
        for inst in instances:
            cost = inst.condition.upkeep_anima_per_round
            if inst.source_character_id and inst.source_character_id != char.id:
                _debit_ally_paid_upkeep(inst, cost)
                continue
            if remaining >= cost:
                remaining -= cost
            else:
                inst.delete()  # lapse — Trigger rows cascade via source_condition FK
        if remaining != anima.current:
            anima.current = remaining
            anima.save(update_fields=["current"])


def _block_if_participant_mid_audere_majora_crossing(encounter: CombatEncounter) -> None:
    """Hard, unconditional block (#1899): a round must never resolve while an
    active participant is mid-Audere-Majora-crossing, regardless of
    ``encounter.is_paused`` — that flag is a separate, softer disconnect-pause
    concern. Extracted to keep ``resolve_round`` under the statement-count lint.
    """
    from world.magic.audere_majora import (  # noqa: PLC0415
        any_character_mid_audere_majora_crossing,
    )

    active_sheets = [
        p.character_sheet
        for p in encounter.participants.filter(status=ParticipantStatus.ACTIVE).select_related(
            "character_sheet"
        )
    ]
    if any_character_mid_audere_majora_crossing(active_sheets):
        raise ActionDispatchError(ActionDispatchError.PARTICIPANT_MID_CROSSING)


def assess_break_bar(
    encounter: CombatEncounter,
    action_outcomes: list[ActionOutcome],
) -> None:
    """Assess break-bar depletion for all boss opponents with a break bar (#2642).

    Diversity-weighted, not per-hit: five feeds (DAMAGE / COMBO / HOLD / DEBUFF /
    SUPPRESSION — ``BreakContributionKind``) are each persisted as a
    ``BreakBarContribution`` row. Depletion sums 1 unit per distinct (actor, kind)
    pair this round, doubled for a pair's first-ever (kind, effect_type)
    occurrence in the encounter, plus the landed combo's flat ``bonus_damage``.
    The result is divided by ``1 + active_unsuppressed_reinforcers`` (the
    lieutenant gate) — floored at 1 unit whenever any depletion occurred, never
    a hard block. When the bar reaches 0, the vulnerability window opens and a
    break celebration broadcasts, naming every distinct contributor.

    Called from resolve_round's post-pass, AFTER the clash post-pass resolves
    this round's clashes (so the HOLD feed can see a LOCK-clash win that
    resolved this same round).
    """
    round_number = encounter.round_number
    bosses = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
            tier=OpponentTier.BOSS,
            break_bar_threshold__gt=0,
            vulnerability_rounds_remaining=0,
        )
    )
    if not bosses:
        return

    for boss in bosses:
        _assess_boss_break_bar(encounter, boss, round_number, action_outcomes)


def _outcome_damaged_boss(outcome: ActionOutcome, boss_pk: int) -> bool:
    """Return True if the outcome's damage results include damage to the given boss."""
    return any(
        hasattr(r, "opponent_id") and r.opponent_id == boss_pk for r in outcome.damage_results
    )


def _assess_boss_break_bar(
    encounter: CombatEncounter,
    boss: CombatOpponent,
    round_number: int,
    action_outcomes: list[ActionOutcome],
) -> None:
    """Assess and apply one boss's break-bar depletion for this round (#2642)."""
    events, combo_bonus = _break_bar_events_this_round(
        encounter, boss, round_number, action_outcomes
    )
    if not events and combo_bonus <= 0:
        return

    raw_depletion = _persist_break_bar_events(boss, round_number, events) + combo_bonus
    if raw_depletion <= 0:
        return

    active_reinforcers = _active_reinforcer_count(boss, round_number)
    # Proportional gate — floor at 1 unit whenever depletion occurred; never a
    # hard block (#2642).
    bar_damage = max(raw_depletion // (1 + active_reinforcers), 1)

    boss.break_bar_current = max(0, boss.break_bar_current - bar_damage)
    broke_this_round = boss.break_bar_current == 0
    if broke_this_round:
        boss.vulnerability_rounds_remaining = boss.vulnerability_rounds
    boss.save(update_fields=["break_bar_current", "vulnerability_rounds_remaining"])
    if broke_this_round:
        _broadcast_break_celebration(encounter, boss)


def _break_bar_events_this_round(
    encounter: CombatEncounter,
    boss: CombatOpponent,
    round_number: int,
    action_outcomes: list[ActionOutcome],
) -> tuple[list[tuple[str, int | None, int | None]], int]:
    """Gather this round's break-bar feed events for *boss*.

    Returns ``(events, combo_bonus)`` where each event is
    ``(kind, participant_id, effect_type_id)`` — one per qualifying feed,
    persisted 1:1 as a ``BreakBarContribution`` row by the caller. Combo's flat
    ``bonus_damage`` depletion is returned separately (additive, not part of
    the diversity-unit pool).
    """
    events: list[tuple[str, int | None, int | None]] = []
    combo_bonus = 0

    # Combo path: first landed combo this round (unchanged bonus_damage depletion,
    # plus its own COMBO diversity-unit contribution).
    for outcome in action_outcomes:
        if outcome.combo_used is not None and _outcome_damaged_boss(outcome, boss.pk):
            combo_bonus = outcome.combo_used.bonus_damage
            events.append(
                (BreakContributionKind.COMBO, outcome.participant_id, outcome.effect_type_id)
            )
            break

    # DAMAGE feed: every qualifying PC damage outcome this round.
    events.extend(
        (BreakContributionKind.DAMAGE, outcome.participant_id, outcome.effect_type_id)
        for outcome in action_outcomes
        if (
            outcome.entity_type == ENTITY_TYPE_PC
            and outcome.participant_id is not None
            and outcome.effect_type_id is not None
            and _outcome_damaged_boss(outcome, boss.pk)
        )
    )

    # HOLD feed: PC-side LOCK-clash win against this boss, resolved this round.
    events.extend(
        (BreakContributionKind.HOLD, participant_id, None)
        for participant_id in _pc_lock_hold_contributors(encounter, boss, round_number)
    )

    round_started_at = encounter.round_started_at

    # DEBUFF feed: new behavior-altering condition landed on the boss this round.
    events.extend(
        (BreakContributionKind.DEBUFF, participant_id, None)
        for participant_id in _boss_new_debuff_events(boss, encounter, round_started_at)
    )

    # SUPPRESSION feed: a reinforcing lieutenant became suppressed this round.
    events.extend(
        (BreakContributionKind.SUPPRESSION, participant_id, None)
        for _lieutenant, participant_id in _newly_suppressed_lieutenants(
            encounter, boss, round_number, round_started_at
        )
    )

    return events, combo_bonus


def _persist_break_bar_events(
    boss: CombatOpponent,
    round_number: int,
    events: list[tuple[str, int | None, int | None]],
) -> int:
    """Persist one ``BreakBarContribution`` row per event; return the diversity-unit total.

    1 unit per distinct (actor, kind) pair this round, doubled to
    ``BREAK_NOVELTY_MULTIPLIER`` for a (kind, effect_type) pair's first-ever
    appearance across the whole encounter (checked against rows persisted in
    prior rounds — never rows created within this same call).
    """
    existing_pairs = set(
        BreakBarContribution.objects.filter(opponent=boss).values_list("kind", "effect_type_id")
    )
    novel_pairs_seen: set[tuple[str, int | None]] = set()
    actor_kind_pairs: set[tuple[int | None, str]] = set()

    for kind, participant_id, effect_type_id in events:
        BreakBarContribution.objects.create(
            opponent=boss,
            participant_id=participant_id,
            round_number=round_number,
            kind=kind,
            effect_type_id=effect_type_id,
        )
        actor_kind_pairs.add((participant_id, kind))
        pair = (kind, effect_type_id)
        if pair not in existing_pairs:
            novel_pairs_seen.add(pair)

    base_units = len(actor_kind_pairs)
    bonus_units = len(novel_pairs_seen) * (BREAK_NOVELTY_MULTIPLIER - 1)
    return base_units + bonus_units


def _pc_lock_hold_contributors(
    encounter: CombatEncounter,
    boss: CombatOpponent,
    round_number: int,
) -> list[int | None]:
    """Participant PKs (or a lone ``None``) crediting a HOLD event per LOCK win this round.

    A LOCK-flavor Clash against *boss* that resolved PC_DECISIVE/PC_MARGINAL this
    round is a PC-side win. Contributors are the PCs with a ``ClashContribution``
    on that clash's resolving-round ``ClashRound`` — falling back to a single
    unattributed (``None``) entry when the clash resolved with no PC contribution
    row (e.g. a pure-abandonment-adjacent edge case).
    """
    won_locks = Clash.objects.filter(
        encounter=encounter,
        npc_opponent=boss,
        flavor=ClashFlavor.LOCK,
        resolved_round=round_number,
        resolution__in=(ClashResolution.PC_DECISIVE, ClashResolution.PC_MARGINAL),
    )
    contributor_ids: list[int | None] = []
    for clash in won_locks:
        character_ids = ClashContribution.objects.filter(
            clash_round__clash=clash,
            clash_round__round_number=round_number,
        ).values_list("character_id", flat=True)
        participant_ids = list(
            CombatParticipant.objects.filter(
                encounter=encounter,
                character_sheet_id__in=character_ids,
            ).values_list("pk", flat=True)
        )
        if participant_ids:
            contributor_ids.extend(participant_ids)
        else:
            contributor_ids.append(None)
    return contributor_ids


def _boss_new_debuff_events(
    boss: CombatOpponent,
    encounter: CombatEncounter,
    round_started_at: datetime | None,
) -> list[int | None]:
    """Participant PKs (or ``None``) crediting a DEBUFF event for *boss* this round."""
    if boss.objectdb_id is None or round_started_at is None:
        return []
    return [
        _participant_id_for_objectdb(encounter, inst.source_character_id)
        for inst in _new_behavior_altering_conditions(boss.objectdb_id, round_started_at)
    ]


def _newly_suppressed_lieutenants(
    encounter: CombatEncounter,
    boss: CombatOpponent,
    round_number: int,
    round_started_at: datetime | None,
) -> list[tuple[CombatOpponent, int | None]]:
    """Lieutenants reinforcing *boss* that became suppressed this round (#2642).

    Round-scoped to the two events with a clean "this round" signal: a new
    behavior-altering condition landing on the lieutenant's ObjectDB
    (``applied_at`` within this round's window), or a new ACTIVE
    ``EngagementLock`` pinning the lieutenant (``started_round == round_number``).
    Status/morale-driven suppression has no per-round timestamp in the schema
    and is not used as a SUPPRESSION trigger — a documented approximation
    (#2642); it still counts toward the lieutenant gate via ``_active_reinforcer_count``.
    """
    lieutenants = list(CombatOpponent.objects.filter(reinforces=boss))
    if not lieutenants:
        return []

    events: list[tuple[CombatOpponent, int | None]] = []
    for lieutenant in lieutenants:
        if lieutenant.objectdb_id is not None and round_started_at is not None:
            for inst in _new_behavior_altering_conditions(lieutenant.objectdb_id, round_started_at):
                participant_id = _participant_id_for_objectdb(encounter, inst.source_character_id)
                events.append((lieutenant, participant_id))
        new_lock = EngagementLock.objects.filter(
            opponent=lieutenant,
            status=EngagementLockStatus.ACTIVE,
            started_round=round_number,
        ).first()
        if new_lock is not None:
            events.append((lieutenant, new_lock.participant_id))
    return events


def _new_behavior_altering_conditions(objectdb_id: int, since: datetime) -> list[ConditionInstance]:
    """Behavior-altering ``ConditionInstance`` rows applied to *objectdb_id* since *since*."""
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    return list(
        ConditionInstance.objects.filter(
            target_id=objectdb_id,
            condition__category__alters_behavior=True,
            applied_at__gte=since,
        ).select_related("condition")
    )


def _has_active_behavior_altering_condition(objectdb_id: int) -> bool:
    """True if *objectdb_id* currently carries an active behavior-altering condition.

    Mirrors ``CharacterSheet.in_control``'s canonical active-condition read
    (ADR-0024): not suppressed, or suppression has expired.
    """
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    not_suppressed = Q(is_suppressed=False)
    suppression_expired = Q(suppressed_until__isnull=False, suppressed_until__lt=timezone.now())
    return ConditionInstance.objects.filter(
        not_suppressed | suppression_expired,
        target_id=objectdb_id,
        condition__category__alters_behavior=True,
    ).exists()


def _participant_id_for_objectdb(encounter: CombatEncounter, objectdb_id: int | None) -> int | None:
    """Resolve an ObjectDB id to the ``CombatParticipant`` pk fielding it in *encounter*."""
    if objectdb_id is None:
        return None
    return (
        CombatParticipant.objects.filter(
            encounter=encounter, character_sheet__character_id=objectdb_id
        )
        .values_list("pk", flat=True)
        .first()
    )


def _active_reinforcer_count(boss: CombatOpponent, round_number: int) -> int:
    """Count *boss*'s active, unsuppressed, acting lieutenants this round (the gate divisor, #2642).

    Active = ``OpponentStatus.ACTIVE``, morale not BREAK, no behavior-altering
    condition on the lieutenant's ObjectDB, not pinned in an ACTIVE
    ``EngagementLock``, and it acted this round (has a ``CombatOpponentAction``
    row). A parked/idle lieutenant does not gate.
    """
    from world.combat.morale import OpponentMoraleState, morale_state_for  # noqa: PLC0415

    lieutenants = list(CombatOpponent.objects.filter(reinforces=boss, status=OpponentStatus.ACTIVE))
    if not lieutenants:
        return 0

    acted_ids = set(
        CombatOpponentAction.objects.filter(
            opponent__in=lieutenants,
            round_number=round_number,
        ).values_list("opponent_id", flat=True)
    )

    count = 0
    for lieutenant in lieutenants:
        if lieutenant.pk not in acted_ids:
            continue
        if morale_state_for(lieutenant) == OpponentMoraleState.BREAK:
            continue
        if lieutenant.objectdb_id is not None and _has_active_behavior_altering_condition(
            lieutenant.objectdb_id
        ):
            continue
        if EngagementLock.objects.filter(
            opponent=lieutenant, status=EngagementLockStatus.ACTIVE
        ).exists():
            continue
        count += 1
    return count


def _broadcast_break_celebration(encounter: CombatEncounter, boss: CombatOpponent) -> None:
    """Broadcast the break moment naming every distinct contributor this encounter (#2642).

    Mirrors ``render_combo_finisher_narration``'s contributor-naming style.
    Broadcasts on both channels — the persisted-interaction/WS payload (web)
    and ``room.msg_contents`` (telnet parity) — since a boss wall breaking is
    exactly the kind of PLAY moment that needs telnet parity.
    """
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        join_labels,
    )

    contributor_labels = _break_bar_contributor_labels(boss)
    if not contributor_labels:
        return

    names = join_labels(contributor_labels)
    narration = f"{boss.name}'s wall breaks — {names} broke through!"
    broadcast_action_outcome(encounter=encounter, narration=narration)
    room = encounter.room
    if room is not None:
        room.msg_contents(narration)


def _break_bar_contributor_labels(boss: CombatOpponent) -> list[str]:
    """Distinct PC labels credited on any ``BreakBarContribution`` row for *boss* this encounter."""
    participant_ids = (
        BreakBarContribution.objects.filter(opponent=boss, participant__isnull=False)
        .values_list("participant_id", flat=True)
        .distinct()
    )
    participants = CombatParticipant.objects.filter(pk__in=participant_ids).select_related(
        "character_sheet"
    )
    return [str(p) for p in participants]


@transaction.atomic
def resolve_round(  # noqa: PLR0915 - orchestration function; already at the
    # single-helper-call budget (see _fire_round_start), and the #1899
    # climactic-moment guard is one more mandatory statement past the limit.
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
            The offense_check_type is now sourced from ``resolve_cast_check_type``
            (the caster's personal check, falling back to the declared technique's
            action_template.check_type only when unprovisioned, ADR-0096) — it is
            no longer passed externally.

    Returns:
        ``RoundResolutionResult`` with outcomes and phase transitions.
    """
    _block_if_participant_mid_audere_majora_crossing(encounter)

    enc = CombatEncounter.objects.select_for_update().get(pk=encounter.pk)
    if enc.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot resolve round: encounter status is "
            f"'{enc.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    # NPC-selection wiring-gap fallback (#2637 design 8): select_npc_actions
    # has zero production callers outside the simulation harness in v1 — no
    # Action/command/task calls it before resolve_round. Auto-select here,
    # while status is still DECLARING (select_npc_actions requires it), when
    # this round has no NPC selection of EITHER shape yet (a normal
    # CombatOpponentAction OR a wind-up's PendingOpponentAttack) — a
    # conservative, idempotent fallback: any explicit prior selection (staff,
    # simulation, tests) is left alone.
    already_selected = (
        CombatOpponentAction.objects.filter(
            opponent__encounter=enc,
            round_number=enc.round_number,
        ).exists()
        or PendingOpponentAttack.objects.filter(
            encounter=enc,
            declared_round=enc.round_number,
        ).exists()
    )
    if not already_selected:
        select_npc_actions(enc)

    enc.status = RoundStatus.RESOLVING
    enc.save(update_fields=["status"])

    round_number = enc.round_number
    result = RoundResolutionResult(round_number=round_number)

    # --- Round-start lifecycle: emit event, drain upkeep, detect combos ---
    result.available_combos = _fire_round_start(enc, round_number)

    # --- Vulnerability window countdown (#2016) ---
    CombatOpponent.objects.filter(
        encounter=encounter,
        vulnerability_rounds_remaining__gt=0,
    ).update(vulnerability_rounds_remaining=F("vulnerability_rounds_remaining") - 1)

    # --- Wind-up maturation (#2637 design 5): before the round's
    # CombatOpponentAction rows are queried below, so a matured wind-up's
    # synthesized action is picked up in the same pass. ---
    _mature_pending_opponent_attacks(enc, round_number)

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
            "focused_ally_target__character_sheet__character",
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
                "opponent_targets",
                queryset=CombatOpponent.objects.all(),
                to_attr="cached_opponent_targets",
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
    _refresh_participant_trigger_handlers(encounter)
    _ensure_reactive_challenges(encounter, pc_actions)
    result.action_outcomes = _resolve_actions(
        resolution_order,
        pc_actions,
        npc_actions,
        defense_check_type,
        defense_check_fn,
        offense_check_fn,
    )

    # --- Combo post-resolution: joint narration + discovery + use-count (#2017) ---
    result.action_outcomes = _process_combo_outcomes(
        result.action_outcomes,
        enc,
        round_number,
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

    # --- Break-bar assessment (#2016, diversity-weighted feeds #2642) ---
    # Runs AFTER the clash post-pass (not before, as pre-#2642) so the HOLD
    # feed can see this round's just-resolved LOCK-clash wins against the boss.
    assess_break_bar(encounter, result.action_outcomes)

    # --- Round-tick: decrement rounds_remaining, tick DoT, fire expiry events,
    # and advance bleed-out for every active participant / opponent.
    # tick_round_for_targets(timing="end") calls process_round_end then
    # advance_bleed_out for each target that has a sheet_data — covering all
    # active bleeding participants (superset of the old pre-filtered query).
    from world.vitals.services import tick_round_for_targets  # noqa: PLC0415

    active_participants = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).select_related("character_sheet__character")
    active_opponents_end = CombatOpponent.objects.filter(
        encounter=encounter,
        status=OpponentStatus.ACTIVE,
    ).select_related("objectdb")
    end_targets = [p.character_sheet.character for p in active_participants]
    end_targets += [opp.objectdb for opp in active_opponents_end if opp.objectdb is not None]
    tick_round_for_targets(end_targets, timing="end")

    # --- Sent Flying explicit resolution (#2638): every unanswered marker
    # resolves now — plummet chain or hard impact. Deliberately AFTER the
    # round-tick pass (a literal ROUNDS/1 duration would race the generic
    # duration countdown above — see world.combat.sent_flying_content) and
    # BEFORE boss/completion status transitions, so a landing impact can still
    # affect this round's completion check. ---
    _resolve_sent_flying_markers(enc)

    # --- Boss phase transitions ---
    result.phase_transitions = _check_boss_transitions(encounter)

    # --- Check encounter completion ---
    # A DUEL may have already been completed mid-round by a YIELD maneuver
    # (yield_duel routes through complete_encounter). Re-fetch status to avoid
    # double-completing or flipping a COMPLETED duel back to BETWEEN_ROUNDS.
    enc.refresh_from_db(fields=["status"])
    if enc.status == RoundStatus.COMPLETED:
        result.encounter_completed = True
    elif enc.encounter_type == EncounterType.DUEL:
        # Duels have their own end conditions (mirror DEFEATED → winner; lethal
        # opponent DEFEATED / PC down). resolve_duel_end completes via the shared
        # seam and returns the encounter, or None if the duel is still ongoing.
        from world.combat.duels import resolve_duel_end  # noqa: PLC0415

        enc.round_started_at = None
        enc.save(update_fields=["round_started_at"])
        if resolve_duel_end(enc) is not None:
            result.encounter_completed = True
        else:
            enc.status = RoundStatus.BETWEEN_ROUNDS
            enc.save(update_fields=["status"])
    elif _check_encounter_completion(encounter):
        result.encounter_completed = True
        enc.round_started_at = None
        enc.save(update_fields=["round_started_at"])
        complete_encounter(enc, outcome=_classify_encounter_outcome(enc))
    else:
        # Note: round_number is NOT advanced here. begin_declaration_phase
        # handles incrementing round_number when transitioning from
        # BETWEEN_ROUNDS to DECLARING for the next round.
        enc.status = RoundStatus.BETWEEN_ROUNDS
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

    cfg = StrainConfig.objects.cached_singleton()
    if cfg is None:
        cfg, _ = StrainConfig.objects.get_or_create(pk=1)
    return cfg


def get_clash_config() -> ClashConfig:
    """Get-or-create the ClashConfig singleton (pk=1)."""
    from world.combat.models import (  # noqa: PLC0415
        ClashConfig,
    )

    cfg = ClashConfig.objects.cached_singleton()
    if cfg is None:
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


# ---------------------------------------------------------------------------
# Equipped-gear combat contribution helpers (#508, Task 7)
# ---------------------------------------------------------------------------
#
# Pure read helpers over ``character.equipped_items`` (the iterable
# CharacterEquipmentHandler, whose rows arrive with item_instance + template +
# quality_tier select_related, so reading effective_* during iteration is
# query-free). They do NOT mutate combat damage logic — that wiring is Tasks
# 8/9. ``_select_equipped_weapon`` is kept separate so the weapon-durability
# decrement task can reuse the same selection.


def _combat_target_bonus(sheet: object, target_name: str, level_override: int | None = None) -> int:
    """get_modifier_total for a named combat ModifierTarget; 0 if the row isn't seeded.

    Combat never hard-depends on seed order (mirrors covenant_level_bonus's
    config-is-None → 0). The target's stat category routes the covenant-role
    equipment walk into the total.

    When ``level_override`` is not supplied, computes the bond-adjusted level via
    ``bond_adjusted_level(sheet)`` (#1165). An unbonded sheet returns None, which
    falls through to ``sheet.current_level`` inside ``covenant_role_bonus`` — zero
    query overhead for the common (non-bonded) case because bond_adjusted_level
    returns None after the fast active-bond check.

    When ``level_override`` is supplied explicitly (e.g. caller already computed
    it), that value is passed directly without a redundant bond lookup.
    """
    from typing import cast  # noqa: PLC0415

    from world.covenants.mentorship import bond_adjusted_level  # noqa: PLC0415
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415
    from world.mechanics.services import get_modifier_total  # noqa: PLC0415

    try:
        target = ModifierTarget.objects.get(name=target_name)
    except ModifierTarget.DoesNotExist:
        return 0
    sheet_typed = cast("CharacterSheet", sheet)
    override = level_override if level_override is not None else bond_adjusted_level(sheet_typed)
    return get_modifier_total(sheet, target, level_override=override)


def _equipped_armor_soak_pieces(
    character: Character,
) -> Iterator[tuple[ItemInstance, int]]:
    """Yield (item_instance, soak) for each worn armor piece with positive soak."""
    from world.items.constants import ARMOR_ARCHETYPES  # noqa: PLC0415

    for equipped in list(character.equipped_items):
        inst = equipped.item_instance
        if inst.template.gear_archetype in ARMOR_ARCHETYPES:
            soak = inst.effective_armor_soak
            if soak > 0:
                yield inst, soak


def effective_soak_from_armor(character: Character) -> int:
    """Sum effective armor soak across the character's equipped armor pieces."""
    return sum(soak for _, soak in _equipped_armor_soak_pieces(character))


def _resonant_armor_soak(character: Character) -> int:
    """The character's un-blended resonant armor-soak pool (#1174).

    eager CharacterModifier total + equipment_walk_total_unblended for the armor_soak
    target. 0 when the sheet or the seeded target row is absent (combat never hard-depends
    on seed order). This is the pool the incompatible-armor ``max`` competes against.
    """
    from world.items.constants import ARMOR_SOAK_TARGET_NAME  # noqa: PLC0415
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415
    from world.mechanics.services import (  # noqa: PLC0415
        equipment_walk_total_unblended,
        get_modifier_breakdown,
    )

    sheet = character.character_sheet
    if sheet is None:
        return 0
    try:
        target = ModifierTarget.objects.get(name=ARMOR_SOAK_TARGET_NAME)
    except ModifierTarget.DoesNotExist:
        return 0
    eager = get_modifier_breakdown(sheet, target).total
    return eager + equipment_walk_total_unblended(sheet, target)


def _split_armor_soak_by_compatibility(
    character: Character,
) -> tuple[int, int, list[ItemInstance], list[ItemInstance]]:
    """Split worn armor's effective soak into role-compatible vs incompatible buckets (#1174).

    A piece is compatible when ANY engaged PRIMARY covenant role is gear-compatible with
    its archetype (existing GearArchetypeCompatibility). With no engaged primary role,
    all armor is incompatible (it then competes via ``max`` against a 0 resonant pool →
    armor-only). PRIMARY-only (#2641, Layer 3 — chassis): a secondary vow never widens
    gear compatibility.

    Returns ``(compat_soak, incompat_soak, compat_pieces, incompat_pieces)`` where the
    piece lists are the ItemInstances whose physical soak fell in each bucket (for
    durability wear).
    """
    from world.covenants.services import is_gear_compatible  # noqa: PLC0415

    engaged_roles = (
        character.covenant_roles.currently_engaged_primary_roles()
        if hasattr(character, "covenant_roles")
        else []
    )
    compat_soak = incompat_soak = 0
    compat_pieces: list[ItemInstance] = []
    incompat_pieces: list[ItemInstance] = []
    for inst, soak in _equipped_armor_soak_pieces(character):
        archetype = inst.template.gear_archetype
        if any(is_gear_compatible(role, archetype) for role in engaged_roles):
            compat_soak += soak
            compat_pieces.append(inst)
        else:
            incompat_soak += soak
            incompat_pieces.append(inst)
    return compat_soak, incompat_soak, compat_pieces, incompat_pieces


def apply_equipped_armor_soak(character: Character, damage: int) -> int:
    """Reduce ``damage`` by role-gated equipped-armor soak (#1174, #2533).

    Worn armor is split by covenant-role compatibility. Compatible soak is then scaled
    by ``gear_additive_fraction`` (#2533) — the character's engaged defense profile(s)
    dial how much of their COMPATIBLE armor stays additive with their vow's own
    defense; 1 (no profile, or every engaged profile at the default 10 tenths) is the
    legacy fully-additive behavior. The resonant soak pool (covenant role base + facet
    + mantle + motif + covenant-level, un-blended) then competes with *incompatible*
    armor via ``max``; the (possibly scaled) compatible armor adds on top:

        compat_soak = int(compat_soak * gear_additive_fraction(character))
        soak = compat_soak + max(incompat_physical, resonant)

    Because ``resonant`` scales on character level and physical armor does not, a role
    incompatible with heavy armor sees its resonant protection overtake platemail past
    low levels. Durability wears only on armor whose physical soak contributes to the
    result (all compatible pieces, regardless of the scaled soak's magnitude; incompatible
    pieces only when they win the ``max`` — unchanged by the #2533 fraction). Returns
    post-soak damage, floored at 0.
    """
    if damage <= 0:
        return damage

    from world.covenants.services import gear_additive_fraction  # noqa: PLC0415
    from world.items.services.durability import decrement_item_durability  # noqa: PLC0415

    compat_soak, incompat_soak, compat_pieces, incompat_pieces = _split_armor_soak_by_compatibility(
        character
    )
    compat_soak = int(compat_soak * gear_additive_fraction(character))
    resonant = _resonant_armor_soak(character)

    incompatible_wins = incompat_soak >= resonant
    soak = compat_soak + (incompat_soak if incompatible_wins else resonant)
    if soak <= 0:
        return damage

    # Wear only armor whose physical soak actually contributed.
    contributors = list(compat_pieces)
    if incompatible_wins:
        contributors += incompat_pieces
    for inst in contributors:
        decrement_item_durability(item_instance=inst)

    return max(0, damage - soak)


def apply_position_cover(character: Character, damage: int, damage_type: DamageType | None) -> int:
    """Subtract attack-cover from damage.

    Reads the character's current position and sums PositionShelter rows with
    applies_to_attacks=True for the given damage type. No-op when the character
    is unpositioned (lenient — matching technique_can_reach) or when damage_type
    is None (untyped damage has no cover).

    Args:
        character: The target character taking damage.
        damage: The incoming damage amount (after armor soak, before condition interactions).
        damage_type: The damage type of the incoming attack (None = untyped, no cover).

    Returns:
        The damage after cover reduction, floored at 0.
    """
    if damage <= 0 or damage_type is None:
        return damage
    from world.areas.positioning.services import (  # noqa: PLC0415
        position_of,
        position_shelter_value,
    )

    position = position_of(character)
    if position is None:
        return damage
    cover = position_shelter_value(position, damage_type, attacks_only=True)
    return max(0, damage - cover)


def _fire_rampart_retaliation(
    profile: RampartElementProfile,
    attacker_ref: object | None,
) -> None:
    """MELEE_RETALIATION signature: burn a melee striker's CombatOpponent back.

    Mirrors ``reflect_damage`` (world/magic/services/effect_handlers.py) —
    ``bypass_pre_apply=True`` terminates re-emission so the retaliation strike
    cannot itself trigger another rampart interception or reflect loop. Never
    retaliates against a PC (ADR-0023): a no-op unless ``attacker_ref``
    resolves to a ``CombatOpponent``.
    """
    if not isinstance(attacker_ref, CombatOpponent):
        return
    if profile.signature_value <= 0:
        return
    apply_damage_to_opponent(
        attacker_ref,
        profile.signature_value,
        bypass_pre_apply=True,
        damage_type=profile.signature_damage_type,
    )


def _rampart_resist(
    profile: RampartElementProfile,
    damage_type: DamageType | None,
    *,
    delivery: str,
    is_area: bool,
) -> int:
    """The resist term for one intercepted strike: base row + MISSILE_WARD adjustment."""
    from world.areas.positioning.constants import RampartSignature  # noqa: PLC0415

    resist = 0
    if damage_type is not None:
        resist = sum(
            profile.resistances.filter(damage_type=damage_type).values_list("value", flat=True)
        )
    if profile.signature_behavior == RampartSignature.MISSILE_WARD:
        if delivery == StrikeDelivery.MISSILE:
            resist += profile.signature_value
        if is_area:
            resist -= profile.signature_value
    return resist


def apply_rampart_interception(  # noqa: PLR0913
    character_or_opponent: Character,  # noqa: OBJECTDB_PARAM - ObjectDB target, mirrors apply_position_cover
    damage: int,
    damage_type: DamageType | None,
    *,
    attacker_ref: object | None,
    delivery: str = StrikeDelivery.MELEE,
    is_area: bool = False,
) -> int:
    """Intercept a strike against a rampart-covered position (#2209).

    Resolves the target's Position via the same lookup ``apply_position_cover``
    uses. No-op (damage passes through unchanged) when the target is
    unpositioned, has no Rampart, or the strike is a sustained attack already
    being drained by an active WARD Clash bound to this rampart — the
    no-double-drain rule; the clash drains instead.

    Math: resist is the profile's resistance row for ``damage_type`` (0 if
    untyped or absent); a MISSILE_WARD profile additionally adds
    ``signature_value`` against MISSILE delivery and subtracts it against area
    strikes. ``chip = max(1, damage - resist)`` (a min-1 floor so barrages
    always crack the rampart). A chip that doesn't clear the rampart's
    remaining integrity fully absorbs the strike (returns 0); a chip that
    clears it collapses the rampart and lets the overflow remainder through.

    Fires MELEE_RETALIATION on interception for a melee strike. GRASPING is
    handled at the forced-move landing seam (``force_move_to_position``), not
    here.

    Returns the damage that should continue through the normal pipeline.
    """
    if damage <= 0:
        return damage
    from world.areas.positioning.constants import RampartSignature  # noqa: PLC0415
    from world.areas.positioning.services import (  # noqa: PLC0415
        damage_rampart,
        position_of,
        rampart_at,
    )

    position = position_of(character_or_opponent)
    if position is None:
        return damage
    rampart = rampart_at(position)
    if rampart is None:
        return damage

    # No-double-drain: a sustained attack already draining via an active WARD
    # clash bound to this rampart skips interception entirely.
    from world.combat.constants import ClashFlavor, ClashStatus  # noqa: PLC0415

    active_ward = Clash.objects.filter(
        rampart=rampart, flavor=ClashFlavor.WARD, status=ClashStatus.ACTIVE
    ).exists()
    if active_ward:
        return damage

    profile = rampart.element_profile
    resist = _rampart_resist(profile, damage_type, delivery=delivery, is_area=is_area)
    chip = max(1, damage - resist)

    if chip < rampart.integrity:
        damage_rampart(rampart, chip)
        pass_through = 0
    else:
        overflow = chip - rampart.integrity
        damage_rampart(rampart, chip)
        pass_through = min(damage, overflow)

    if delivery == StrikeDelivery.MELEE and profile.signature_behavior == (
        RampartSignature.MELEE_RETALIATION
    ):
        _fire_rampart_retaliation(profile, attacker_ref)

    return pass_through


def elevation_bonus(
    attacker_sheet: CharacterSheet, attacker_pos: Position, target_pos: Position
) -> int:
    """Flat to-hit bonus when attacker is elevated/aerial and target is not.

    Returns 0 in all other cases (both elevated, both ground, attacker
    ground / target elevated). Offensive-only — no penalty for firing up.
    The magnitude comes from the 'elevation_advantage' ModifierTarget
    (staff-authored via CharacterModifier).
    """
    from world.areas.positioning.constants import PositionKind  # noqa: PLC0415

    elevated_kinds = {PositionKind.ELEVATED, PositionKind.AERIAL}
    if attacker_pos.kind not in elevated_kinds:
        return 0
    if target_pos.kind in elevated_kinds:
        return 0
    return _combat_target_bonus(attacker_sheet, ELEVATION_ADVANTAGE_TARGET_NAME)


def _select_equipped_weapon(character: Character) -> ItemInstance | None:
    """The character's strongest equipped weapon instance (>0 effective damage).

    Deterministic: max by effective_weapon_damage, tie-break by item_instance pk
    (lowest pk wins, via negating pk in the comparison key).
    """
    from world.items.constants import WEAPON_ARCHETYPES  # noqa: PLC0415

    best = None
    for equipped in character.equipped_items:
        inst = equipped.item_instance
        if inst.template.gear_archetype not in WEAPON_ARCHETYPES:
            continue
        dmg = inst.effective_weapon_damage
        if dmg <= 0:
            continue
        key = (dmg, -inst.pk)
        if best is None or key > best[0]:
            best = (key, inst)
    return best[1] if best is not None else None


def effective_weapon_profile(character: Character) -> WeaponContribution | None:
    """The character's strongest equipped weapon as a combat contribution."""
    from world.combat.types import WeaponContribution  # noqa: PLC0415

    inst = _select_equipped_weapon(character)
    if inst is None:
        return None
    return WeaponContribution(
        damage=inst.effective_weapon_damage,
        damage_type=inst.effective_weapon_damage_type,
    )


def _weapon_augmented_budget(
    profile: AbstractDamageProfile,
    budget: int,
    weapon: WeaponContribution | None,
    sheet: object | None = None,
) -> tuple[int, DamageType | None]:
    """Fold an equipped weapon's contribution into a damage profile's budget.

    For a ``uses_equipped_weapon`` profile with an equipped weapon, adds the
    weapon's damage to the formula budget, then the covenant-role weapon-damage
    bonus (via ``_combat_target_bonus``) when a sheet is supplied. If the
    profile authored no damage_type of its own, the weapon's type is used.
    Returns ``(budget, damage_type)``; non-weapon profiles (or an unarmed
    attacker) pass through unchanged.
    """
    profile_damage_type = profile.damage_type
    if profile.uses_equipped_weapon and weapon is not None:
        budget += weapon.damage
        if sheet is not None:
            from world.items.constants import WEAPON_DAMAGE_TARGET_NAME  # noqa: PLC0415

            budget += _combat_target_bonus(sheet, WEAPON_DAMAGE_TARGET_NAME)
        if profile_damage_type is None:
            profile_damage_type = weapon.damage_type
    return budget, profile_damage_type


def _wear_equipped_weapon(character: Character) -> None:
    """Apply one point of durability wear to the character's strongest weapon.

    Called once per landed weapon-based attack (not once per damage profile), so
    a multi-component technique does not double-wear the weapon.
    """
    weapon_inst = _select_equipped_weapon(character)
    if weapon_inst is None:
        return
    from world.items.services.durability import decrement_item_durability  # noqa: PLC0415

    decrement_item_durability(item_instance=weapon_inst)
