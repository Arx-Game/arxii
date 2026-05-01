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

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.checks.types import CheckResult
    from world.conditions.models import ConditionTemplate
    from world.covenants.models import CovenantRole
    from world.magic.models import Technique
    from world.magic.types import TechniqueUseResult
    from world.scenes.models import Persona

    PerformCheckFn = Callable[..., CheckResult]

from flows.constants import EventName
from flows.emit import emit_event
from flows.events.payloads import (
    AttackPreResolvePayload,
    CharacterIncapacitatedPayload,
    CharacterKilledPayload,
    DamageAppliedPayload,
    DamagePreApplyPayload,
)
from world.checks.services import perform_check
from world.combat.constants import (
    DEFENSE_CRITICAL_MULTIPLIER,
    DEFENSE_FULL_MULTIPLIER,
    DEFENSE_NO_DAMAGE_THRESHOLD,
    DEFENSE_REDUCED_MULTIPLIER,
    DEFENSE_REDUCED_THRESHOLD,
    ENTITY_TYPE_NPC,
    ENTITY_TYPE_PC,
    NO_ROLE_SPEED_RANK,
    NPC_SPEED_RANK,
    OFFENSE_FULL_THRESHOLD,
    OFFENSE_HALF_THRESHOLD,
    ActionCategory,
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
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    CombatRoundAction,
    ComboDefinition,
    ComboLearning,
    ComboSlot,
    ThreatPool,
    ThreatPoolEntry,
)
from world.combat.types import (
    ActionOutcome,
    AvailableCombo,
    CombatTechniqueResolution,
    CombatTechniqueResult,
    ComboSlotMatch,
    DefenseResult,
    OpponentDamageResult,
    ParticipantDamageResult,
    RoundResolutionResult,
)
from world.fatigue.constants import EFFORT_CHECK_MODIFIER, EffortLevel, FatigueCategory
from world.fatigue.services import apply_fatigue, get_fatigue_penalty
from world.magic.constants import EffectKind
from world.vitals.constants import (
    DEATH_HEALTH_THRESHOLD,
    KNOCKOUT_HEALTH_THRESHOLD,
    PERMANENT_WOUND_THRESHOLD,
    CharacterStatus,
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


# ---------------------------------------------------------------------------
# CombatAttackResolver - Damage resolution for combat techniques
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CombatAttackResolver:
    """Resolves the inner damage step of a combat-cast attack technique.

    Built by resolve_combat_technique() and passed to use_technique() as
    resolve_fn. State is inspectable at any point during/after the cast,
    which closures don't allow. Subclassable when non-attack effect types
    arrive (next PR): CombatBuffResolver, CombatDefenseResolver, etc.
    """

    participant: CombatParticipant
    action: CombatRoundAction
    target: CombatOpponent
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
        extra_modifiers = effort_mod + self.pull_flat_bonus
        character = self.participant.character_sheet.character
        return check_fn(
            character,
            self.offense_check_type,
            extra_modifiers=extra_modifiers,
            fatigue_penalty=penalty,
        )

    def _scale(self, check_result: CheckResult) -> int:
        """Scale base_power by success_level: full / half / zero."""
        base_power = self.action.focused_action.effect_type.base_power
        if base_power is None:
            return 0
        if check_result.success_level >= OFFENSE_FULL_THRESHOLD:
            return base_power
        if check_result.success_level >= OFFENSE_HALF_THRESHOLD:
            return base_power // 2
        return 0

    def _apply(self, scaled_damage: int) -> list[OpponentDamageResult]:
        """Apply damage to target if alive and damage > 0."""
        if scaled_damage <= 0:
            return []
        self.target.refresh_from_db()
        if self.target.status == OpponentStatus.DEFEATED:
            return []
        return [apply_damage_to_opponent(self.target, scaled_damage)]

    def __call__(self) -> CombatTechniqueResolution:
        check_result = self._roll_check()
        scaled_damage = self._scale(check_result)
        damage_results = self._apply(scaled_damage)
        return CombatTechniqueResolution(
            check_result=check_result,
            damage_results=damage_results,
            pull_flat_bonus=self.pull_flat_bonus,
            scaled_damage=scaled_damage,
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


def _build_combat_result(
    technique_use_result: TechniqueUseResult,
    resolver: CombatAttackResolver,  # noqa: ARG001 - kept for future extensibility
) -> CombatTechniqueResult:
    """Translate use_technique's outcome into the adapter's return shape."""
    if not technique_use_result.confirmed:
        return CombatTechniqueResult(
            damage_results=[],
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
        technique_use_result=technique_use_result,
    )


def resolve_combat_technique(  # noqa: PLR0913 — keyword-only orchestrator args
    *,
    participant: CombatParticipant,
    action: CombatRoundAction,
    target: CombatOpponent,
    fatigue_category: str,
    offense_check_type: CheckType,
    offense_check_fn: PerformCheckFn | None,
) -> CombatTechniqueResult:
    """Route a damage-path combat technique through use_technique.

    Builds a CombatAttackResolver and passes it to use_technique as
    resolve_fn. The magic envelope handles anima, soulfray, mishap,
    PRE_CAST/CAST events, reactive scar interception, and corruption.
    The resolver does the offense check + damage application inside
    that envelope.

    Soulfray warning is auto-confirmed at round resolution time —
    frontend handles preview before submission.

    AFFECTED-per-target events are deferred (CombatOpponent is not an
    ObjectDB; targets=[] until the opponent <-> ObjectDB relationship
    is decided).

    Other pull effect kinds are deferred:
    - INTENSITY_BUMP: needs runtime stats to accept combat context
    - CAPABILITY_GRANT: tied to non-attack pipeline
    - NARRATIVE_ONLY: cosmetic surfacing
    - VITAL_BONUS: already wired through recompute_max_health_with_threads
    """
    from world.magic.services import use_technique  # noqa: PLC0415

    encounter = participant.encounter
    pull_flat_bonus = _sum_active_flat_bonuses(participant, encounter)

    resolver = CombatAttackResolver(
        participant=participant,
        action=action,
        target=target,
        pull_flat_bonus=pull_flat_bonus,
        fatigue_category=fatigue_category,
        offense_check_type=offense_check_type,
        offense_check_fn=offense_check_fn,
    )

    technique_use_result = use_technique(
        character=participant.character_sheet.character,
        technique=action.focused_action,
        resolve_fn=resolver,
        confirm_soulfray_risk=True,
        targets=[],
    )

    return _build_combat_result(technique_use_result, resolver)


# ---------------------------------------------------------------------------
# ActionCategory -> FatigueCategory mapping (same values)
# ---------------------------------------------------------------------------

_ACTION_TO_FATIGUE_CATEGORY: dict[str, str] = {
    ActionCategory.PHYSICAL: FatigueCategory.PHYSICAL,
    ActionCategory.SOCIAL: FatigueCategory.SOCIAL,
    ActionCategory.MENTAL: FatigueCategory.MENTAL,
}


def add_participant(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
    *,
    covenant_role: CovenantRole | None = None,
) -> CombatParticipant:
    """Create a CombatParticipant linking a PC to an encounter."""
    return CombatParticipant.objects.create(
        encounter=encounter,
        character_sheet=character_sheet,
        covenant_role=covenant_role,
    )


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

    return CombatParticipant.objects.create(
        encounter=encounter,
        character_sheet=character_sheet,
        covenant_role=covenant_role,
        status=ParticipantStatus.ACTIVE,
    )


def declare_flee(participant: CombatParticipant) -> CombatRoundAction:
    """Declare intent to flee -- passives-only action, auto-ready.

    Creates a CombatRoundAction with no focused action. Marks the
    participant as FLED. Flee auto-succeeds in Phase 3 -- the participant
    is removed from active combat at round resolution.

    Phase 4 will add flee checks and covering actions.
    """
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    encounter = participant.encounter

    # Encounter status check
    if encounter.status != EncounterStatus.DECLARING:
        msg = (
            f"Cannot flee: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    # Vitality check — dead characters cannot flee
    vitals = CharacterVitals.objects.get(
        character_sheet=participant.character_sheet,
    )
    if vitals.status not in (CharacterStatus.ALIVE, CharacterStatus.UNCONSCIOUS):
        msg = f"Cannot flee: character status is '{vitals.get_status_display()}'."
        raise ValueError(msg)
    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.VERY_LOW,
            "focused_opponent_target": None,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    participant.status = ParticipantStatus.FLED
    participant.save(update_fields=["status"])
    return action


def add_opponent(  # noqa: PLR0913 - opponent creation requires all stat fields
    encounter: CombatEncounter,
    *,
    name: str,
    tier: str,
    max_health: int,
    threat_pool: ThreatPool,
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

    from world.combat.typeclasses.combat_npc import CombatNPC  # noqa: PLC0415

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
        objectdb = create_object(CombatNPC, key=name, location=encounter.room)
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


def declare_action(  # noqa: PLR0913 - action declaration requires all slot fields
    participant: CombatParticipant,
    *,
    focused_action: Technique | None = None,
    focused_category: str | None = None,
    effort_level: str,
    focused_opponent_target: CombatOpponent | None = None,
    physical_passive: Technique | None = None,
    social_passive: Technique | None = None,
    mental_passive: Technique | None = None,
) -> CombatRoundAction:
    """Declare a PC's action for the current round.

    Validations:
    - Participant must be ALIVE (or DYING with dying_final_round=True).
    - Encounter must be in DECLARING status.
    - Round number must match encounter's current round.
    - The passive slot matching the focused_category must be None.

    Raises ValueError with clear messages for validation failures.
    """

    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    encounter = participant.encounter

    # Status check
    vitals = CharacterVitals.objects.get(character_sheet=participant.character_sheet)
    is_alive = vitals.status == CharacterStatus.ALIVE
    is_dying_final = vitals.status == CharacterStatus.DYING and vitals.dying_final_round
    if not (is_alive or is_dying_final):
        msg = f"Cannot declare action: character status is '{vitals.get_status_display()}'."
        raise ValueError(msg)

    # Encounter status check
    if encounter.status != EncounterStatus.DECLARING:
        msg = (
            f"Cannot declare action: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    # Passive slot validation (only when a focused category is declared)
    if focused_category is not None:
        passive_map = {
            ActionCategory.PHYSICAL: physical_passive,
            ActionCategory.SOCIAL: social_passive,
            ActionCategory.MENTAL: mental_passive,
        }
        conflicting_passive = passive_map.get(focused_category)
    else:
        conflicting_passive = None
    if conflicting_passive is not None:
        msg = (
            f"Cannot declare action: {focused_category} passive must be "
            f"None when focused_category is {focused_category}."
        )
        raise ValueError(msg)

    if focused_opponent_target and focused_opponent_target.status != OpponentStatus.ACTIVE:
        msg = "Cannot target a defeated opponent."
        raise ValueError(msg)

    action, _created = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": focused_action,
            "focused_category": focused_category,
            "effort_level": effort_level,
            "focused_opponent_target": focused_opponent_target,
            "physical_passive": physical_passive,
            "social_passive": social_passive,
            "mental_passive": mental_passive,
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

    # Design: only ALIVE PCs are targetable. DYING PCs (on their final round)
    # get one free offensive action without being targeted — "going out swinging."
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    alive_sheet_ids = set(
        CharacterVitals.objects.filter(
            status=CharacterStatus.ALIVE,
            character_sheet__combat_participations__encounter=encounter,
            character_sheet__combat_participations__status=ParticipantStatus.ACTIVE,
        ).values_list("character_sheet_id", flat=True)
    )
    active_participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            character_sheet_id__in=alive_sheet_ids,
            status=ParticipantStatus.ACTIVE,
        )
    )

    actions: list[CombatOpponentAction] = []

    for opponent in opponents:
        pool_entries = entries_by_pool.get(opponent.threat_pool_id, [])
        cooldown_used = recently_used_by_opponent.get(opponent.pk, set())
        eligible = _get_eligible_entries(opponent, pool_entries, cooldown_used)
        if not eligible:
            continue

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


def apply_damage_to_opponent(
    opponent: CombatOpponent,
    raw_damage: int,
    *,
    bypass_soak: bool = False,
) -> OpponentDamageResult:
    """Apply damage to an NPC opponent, accounting for soak and probing.

    All raw damage (even fully soaked) contributes to probing. Only damage
    that exceeds soak actually reduces health.
    """
    effective_soak = 0 if bypass_soak else opponent.soak_value
    damage_through = max(0, raw_damage - effective_soak)
    # Combo damage that bypasses soak should not also probe — the combo
    # itself is the reward for probing.
    probing_increment = 0 if bypass_soak else max(0, raw_damage)

    opponent.health -= damage_through
    opponent.probing_current += probing_increment

    defeated = opponent.health <= 0
    if defeated:
        opponent.status = OpponentStatus.DEFEATED

    opponent.save(update_fields=["health", "probing_current", "status"])

    return OpponentDamageResult(
        damage_dealt=damage_through,
        health_damaged=damage_through > 0,
        probed=probing_increment > 0,
        probing_increment=probing_increment,
        defeated=defeated,
    )


def apply_damage_to_participant(
    participant: CombatParticipant,
    damage: int,
    *,
    force_death: bool = False,
    damage_type: str = "physical",
    source: object | None = None,
) -> ParticipantDamageResult:
    """Apply damage to a PC via their CharacterVitals.

    Does NOT roll for knockout/death/wounds — only reports eligibility.
    The caller is responsible for acting on the result.

    Emits reactive events:
    - DAMAGE_PRE_APPLY (cancellable, mutable amount)
    - DAMAGE_APPLIED (post-save, frozen)
    - CHARACTER_INCAPACITATED (if knockout_eligible)
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

    vitals.health -= effective_damage
    health_after = vitals.health

    if vitals.max_health > 0:
        health_pct = max(0.0, health_after / vitals.max_health)
    else:
        health_pct = 0.0

    knockout_eligible = (
        health_pct <= KNOCKOUT_HEALTH_THRESHOLD and health_after > DEATH_HEALTH_THRESHOLD
    )
    death_eligible = health_after <= DEATH_HEALTH_THRESHOLD
    permanent_wound_eligible = effective_damage > (vitals.max_health * PERMANENT_WOUND_THRESHOLD)

    update_fields = ["health"]
    if force_death:
        vitals.status = CharacterStatus.DYING
        vitals.dying_final_round = True
        update_fields.extend(["status", "dying_final_round"])

    vitals.save(update_fields=update_fields)

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
        if knockout_eligible:
            emit_event(
                EventName.CHARACTER_INCAPACITATED,
                CharacterIncapacitatedPayload(
                    character=character,
                    source_event=EventName.DAMAGE_PRE_APPLY,
                ),
                location=room,
            )

        if death_eligible or force_death:
            emit_event(
                EventName.CHARACTER_KILLED,
                CharacterKilledPayload(
                    character=character,
                    source_event=EventName.DAMAGE_PRE_APPLY,
                ),
                location=room,
            )

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
    - ALIVE PCs (speed from covenant_role or NO_ROLE_SPEED_RANK)
    - DYING PCs with dying_final_round=True (their last action)
    - ACTIVE NPCs (all at NPC_SPEED_RANK)

    Excludes:
    - UNCONSCIOUS PCs
    - DEAD PCs
    - DYING PCs without dying_final_round
    - DEFEATED/FLED NPCs
    """
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        ).select_related("covenant_role", "character_sheet")
    )

    sheet_ids = [p.character_sheet_id for p in participants]
    vitals_map: dict[int, CharacterVitals] = {
        v.character_sheet_id: v
        for v in CharacterVitals.objects.filter(character_sheet_id__in=sheet_ids)
    }

    ranked: list[tuple[int, str, CombatParticipant | CombatOpponent]] = []
    for p in participants:
        vitals = vitals_map.get(p.character_sheet_id)
        if vitals is None:
            logger.warning(
                "Participant %s has no CharacterVitals record — excluded from resolution",
                p.character_sheet,
            )
            continue
        status = vitals.status
        if status == CharacterStatus.ALIVE or (
            status == CharacterStatus.DYING and vitals.dying_final_round
        ):
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
    active_opponents = CombatOpponent.objects.filter(
        encounter=encounter,
        status=OpponentStatus.ACTIVE,
    )
    for opp in active_opponents:
        max_probing = max(max_probing, opp.probing_current)
    available: list[AvailableCombo] = []

    for combo in combos:
        slots: list[ComboSlot] = combo.cached_slots
        if not slots:
            continue

        # Check minimum probing requirement
        if combo.minimum_probing is not None and max_probing < combo.minimum_probing:
            continue

        # Determine if any participant knows the combo
        knowers = known_map.get(combo.pk, set())
        known_by_any = bool(knowers & participant_sheet_ids)
        if not known_by_any and not combo.discoverable_via_combat:
            continue

        # Backtracking slot matching: each slot must be filled by a distinct action
        slot_matches = _try_match_all_slots(slots, actions, gift_resonance_ids)
        if slot_matches is None:
            continue

        available.append(
            AvailableCombo(
                combo=combo,
                slot_matches=slot_matches,
                known_by_participant=known_by_any,
            )
        )

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
        damage_type=opponent_action.threat_entry.attack_category,
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


def _resolve_pc_action(
    participant: CombatParticipant,
    action: CombatRoundAction,
    offense_check_fn: PerformCheckFn | None = None,
    offense_check_type: CheckType | None = None,
) -> ActionOutcome:
    """Resolve a single PC's focused action during round resolution.

    For non-combo actions, uses perform_check if an offense_check_type is
    provided. The check result's success_level scales damage:
    - success_level >= 2: full base_power
    - success_level == 1: half base_power
    - success_level <= 0: zero (miss)

    Fatigue is applied after the action resolves (both combo and non-combo).
    """
    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))

    technique = action.focused_action
    if technique is None:
        # Passives-only round (e.g. flee) — no focused action to resolve.
        return outcome

    target = action.focused_opponent_target
    fatigue_category = _ACTION_TO_FATIGUE_CATEGORY.get(
        action.focused_category, FatigueCategory.PHYSICAL
    )

    if target is not None:
        target.refresh_from_db()
        if target.status != OpponentStatus.DEFEATED:
            if action.combo_upgrade:
                combo = action.combo_upgrade
                dmg_result = apply_damage_to_opponent(
                    target,
                    combo.bonus_damage,
                    bypass_soak=combo.bypass_soak,
                )
                outcome.combo_used = combo
                outcome.damage_results.append(dmg_result)
            elif technique.effect_type.base_power is not None:
                # Damage path — route through magic pipeline (use_technique).
                # Non-attack effect types (base_power is None) stay no-op until
                # the conditions-from-techniques resolver lands (next PR).
                if offense_check_type is not None:
                    combat_result = resolve_combat_technique(
                        participant=participant,
                        action=action,
                        target=target,
                        fatigue_category=fatigue_category,
                        offense_check_type=offense_check_type,
                        offense_check_fn=offense_check_fn,
                    )
                    outcome.damage_results.extend(combat_result.damage_results)
                else:
                    # TODO(combat-magic-pipeline): Remove this bypass once all combat
                    # tests/fixtures provide an offense_check_type. Without one, this
                    # branch skips the magic pipeline entirely (no anima cost, no events,
                    # no soulfray), which is a temporary test-compatibility shim, not
                    # production behavior.
                    dmg_result = apply_damage_to_opponent(target, technique.effect_type.base_power)
                    outcome.damage_results.append(dmg_result)

    # Apply fatigue after action resolves
    apply_fatigue(
        participant.character_sheet,
        fatigue_category,
        technique.anima_cost,
        action.effort_level,
    )

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

    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    # Batch-fetch vitals for all targets
    sheet_ids = [t.character_sheet_id for t in targets]
    vitals_by_sheet: dict[int, CharacterVitals] = {
        v.character_sheet_id: v
        for v in CharacterVitals.objects.filter(character_sheet_id__in=sheet_ids)
    }

    condition_applications: list[tuple[ObjectDB, ConditionTemplate]] = []

    for target_participant in targets:
        vitals_obj = vitals_by_sheet.get(target_participant.character_sheet_id)
        if vitals_obj is None or vitals_obj.status != CharacterStatus.ALIVE:
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
                damage_type=npc_action.threat_entry.attack_category,
                source=opponent,
            )
        outcome.damage_results.append(dmg_result)

        # Survivability pipeline — knockout, death, wound checks
        from world.vitals.services import process_damage_consequences  # noqa: PLC0415

        consequence = process_damage_consequences(
            character=target_participant.character_sheet.character,
            damage_dealt=dmg_result.damage_dealt,
            damage_type=None,  # TODO: get from threat entry when damage types are authored
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

    return outcome


def _resolve_actions(  # noqa: PLR0913 - resolution needs all check params
    resolution_order: list[tuple[str, CombatParticipant | CombatOpponent]],
    pc_actions: dict[int, CombatRoundAction],
    npc_actions: dict[int, CombatOpponentAction],
    defense_check_type: CheckType | None,
    defense_check_fn: PerformCheckFn | None,
    offense_check_fn: PerformCheckFn | None,
    offense_check_type: CheckType | None,
) -> list[ActionOutcome]:
    """Iterate resolution order and resolve each entity's action."""
    outcomes: list[ActionOutcome] = []
    for entity_type, entity in resolution_order:
        if entity_type == ENTITY_TYPE_PC:
            if not isinstance(entity, CombatParticipant):
                continue
            action = pc_actions.get(entity.pk)
            if action is not None:
                outcomes.append(
                    _resolve_pc_action(entity, action, offense_check_fn, offense_check_type)
                )

        elif entity_type == ENTITY_TYPE_NPC:
            if not isinstance(entity, CombatOpponent):
                continue
            npc_action = npc_actions.get(entity.pk)
            if npc_action is not None:
                outcomes.append(
                    _resolve_npc_action(entity, npc_action, defense_check_type, defense_check_fn),
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
    """Return True if the encounter should be marked complete."""
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    all_opponents_down = not CombatOpponent.objects.filter(
        encounter=encounter,
        status=OpponentStatus.ACTIVE,
    ).exists()

    participant_sheet_ids = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).values_list("character_sheet_id", flat=True)

    all_pcs_down = not CharacterVitals.objects.filter(
        character_sheet_id__in=participant_sheet_ids,
        status=CharacterStatus.ALIVE,
    ).exists()

    return all_opponents_down or all_pcs_down


@transaction.atomic
def resolve_round(
    encounter: CombatEncounter,
    *,
    defense_check_fn: PerformCheckFn | None = None,
    defense_check_type: CheckType | None = None,
    offense_check_fn: PerformCheckFn | None = None,
    offense_check_type: CheckType | None = None,
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
         bypass. Otherwise use perform_check (if offense_check_type provided)
         to scale damage by success level. Apply fatigue after each action.
       - For each **NPC**: resolve each targeted PC's defensive check.
         Process knockout/death transitions and apply conditions.
    4. Consume dying final rounds: DYING PCs with dying_final_round become DEAD.
    5. After all actions: check boss phase transitions for boss-tier opponents.
    6. Check encounter completion (all opponents defeated or all PCs down).
    7. Transition encounter to ``BETWEEN_ROUNDS`` or ``COMPLETED``.

    Args:
        encounter: The combat encounter to resolve.
        defense_check_fn: Optional ``perform_check`` override for PC defense.
        defense_check_type: The CheckType used for defensive rolls.
        offense_check_fn: Optional ``perform_check`` override for PC offense.
        offense_check_type: The CheckType used for offensive rolls.

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
    for action in CombatRoundAction.objects.filter(
        participant__encounter=encounter,
        round_number=round_number,
    ).select_related(
        "participant",
        "participant__character_sheet",
        "focused_action",
        "focused_action__effect_type",
        "focused_opponent_target",
        "combo_upgrade",
    ):
        pc_actions[action.participant_id] = action

    npc_actions: dict[int, CombatOpponentAction] = {}
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
        npc_actions[npc_action.opponent_id] = npc_action

    # --- Resolve in speed-rank order ---
    resolution_order = get_resolution_order(encounter)
    result.action_outcomes = _resolve_actions(
        resolution_order,
        pc_actions,
        npc_actions,
        defense_check_type,
        defense_check_fn,
        offense_check_fn,
        offense_check_type,
    )

    # --- Dying final round consumption ---
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    participant_sheet_ids = CombatParticipant.objects.filter(
        encounter=encounter,
    ).values_list("character_sheet_id", flat=True)

    dying_vitals = CharacterVitals.objects.filter(
        character_sheet_id__in=participant_sheet_ids,
        status=CharacterStatus.DYING,
        dying_final_round=True,
    )
    for vitals in dying_vitals:
        vitals.dying_final_round = False
        vitals.status = CharacterStatus.DEAD
        vitals.save(update_fields=["status", "dying_final_round"])

    # --- Boss phase transitions ---
    result.phase_transitions = _check_boss_transitions(encounter)

    # --- Check encounter completion ---
    if _check_encounter_completion(encounter):
        enc.status = EncounterStatus.COMPLETED
        result.encounter_completed = True
        cleanup_completed_encounter(encounter)
    else:
        # Note: round_number is NOT advanced here. begin_declaration_phase
        # handles incrementing round_number when transitioning from
        # BETWEEN_ROUNDS to DECLARING for the next round.
        enc.status = EncounterStatus.BETWEEN_ROUNDS

    enc.round_started_at = None
    enc.save(update_fields=["status", "round_started_at"])
    encounter.refresh_from_db()

    return result
