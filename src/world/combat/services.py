"""Service functions for combat encounter lifecycle."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
import logging
import math
import random
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Prefetch, Q

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.checks.types import CheckResult
    from world.conditions.models import ConditionTemplate
    from world.covenants.models import CovenantRole
    from world.magic.models import Technique
    from world.scenes.models import Persona

    PerformCheckFn = Callable[..., CheckResult]

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
    TargetingMode,
    TargetSelection,
)
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
    ComboSlotMatch,
    DefenseResult,
    OpponentDamageResult,
    ParticipantDamageResult,
    RoundResolutionResult,
)
from world.fatigue.constants import EFFORT_CHECK_MODIFIER, FatigueCategory
from world.fatigue.services import apply_fatigue, get_fatigue_penalty
from world.vitals.constants import (
    DEATH_HEALTH_THRESHOLD,
    KNOCKOUT_HEALTH_THRESHOLD,
    PERMANENT_WOUND_THRESHOLD,
    CharacterStatus,
)

logger = logging.getLogger(__name__)

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
) -> CombatOpponent:
    """Create a CombatOpponent with health equal to max_health."""
    return CombatOpponent.objects.create(
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
    )


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
    enc.save(update_fields=["round_number", "status"])
    # Refresh the caller's instance so it reflects the new state.
    encounter.refresh_from_db()


def declare_action(  # noqa: PLR0913 - action declaration requires all slot fields
    participant: CombatParticipant,
    *,
    focused_action: Technique,
    focused_category: str,
    effort_level: str,
    focused_target: CombatOpponent | None = None,
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

    # Passive slot validation
    passive_map = {
        ActionCategory.PHYSICAL: physical_passive,
        ActionCategory.SOCIAL: social_passive,
        ActionCategory.MENTAL: mental_passive,
    }
    conflicting_passive = passive_map.get(focused_category)
    if conflicting_passive is not None:
        msg = (
            f"Cannot declare action: {focused_category} passive must be "
            f"None when focused_category is {focused_category}."
        )
        raise ValueError(msg)

    return CombatRoundAction.objects.create(
        participant=participant,
        round_number=encounter.round_number,
        focused_category=focused_category,
        effort_level=effort_level,
        focused_action=focused_action,
        focused_target=focused_target,
        physical_passive=physical_passive,
        social_passive=social_passive,
        mental_passive=mental_passive,
    )


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
        ).values_list("character_sheet_id", flat=True)
    )
    active_participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            character_sheet_id__in=alive_sheet_ids,
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
) -> ParticipantDamageResult:
    """Apply damage to a PC via their CharacterVitals.

    Does NOT roll for knockout/death/wounds — only reports eligibility.
    The caller is responsible for acting on the result.
    """
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    vitals = CharacterVitals.objects.get(
        character_sheet=participant.character_sheet,
    )

    vitals.health -= damage
    health_after = vitals.health

    if vitals.max_health > 0:
        health_pct = max(0.0, health_after / vitals.max_health)
    else:
        health_pct = 0.0

    knockout_eligible = (
        health_pct <= KNOCKOUT_HEALTH_THRESHOLD and health_after > DEATH_HEALTH_THRESHOLD
    )
    death_eligible = health_after <= DEATH_HEALTH_THRESHOLD
    permanent_wound_eligible = damage > (vitals.max_health * PERMANENT_WOUND_THRESHOLD)

    update_fields = ["health"]
    if force_death:
        vitals.status = CharacterStatus.DYING
        vitals.dying_final_round = True
        update_fields.extend(["status", "dying_final_round"])

    vitals.save(update_fields=update_fields)

    return ParticipantDamageResult(
        damage_dealt=damage,
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
    result: CheckResult = perform_check_fn(character, check_type)

    multiplier = _damage_multiplier_for_success(result.success_level)
    base_damage = opponent_action.threat_entry.base_damage
    final_damage = math.floor(base_damage * multiplier)

    damage_result = apply_damage_to_participant(participant, final_damage)

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

    target = action.focused_target
    technique = action.focused_action
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
            else:
                base_power = technique.effect_type.base_power
                if base_power is not None:
                    raw = base_power
                    if offense_check_type is not None:
                        check_fn = offense_check_fn
                        if check_fn is None:
                            from world.checks.services import (  # noqa: PLC0415
                                perform_check as check_fn,
                            )
                        penalty = get_fatigue_penalty(participant.character_sheet, fatigue_category)
                        effort_mod = EFFORT_CHECK_MODIFIER.get(action.effort_level, 0)
                        character = participant.character_sheet.character
                        result = check_fn(
                            character,
                            offense_check_type,
                            extra_modifiers=effort_mod,
                            fatigue_penalty=penalty,
                        )
                        if result.success_level >= OFFENSE_FULL_THRESHOLD:
                            scaled = raw
                        elif result.success_level >= OFFENSE_HALF_THRESHOLD:
                            scaled = raw // 2
                        else:
                            scaled = 0
                    else:
                        scaled = raw
                    if scaled > 0:
                        dmg_result = apply_damage_to_opponent(target, scaled)
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
            )
        outcome.damage_results.append(dmg_result)

        # Knockout/death processing — only transition from ALIVE
        vitals_obj.refresh_from_db()
        if dmg_result.death_eligible and vitals_obj.status == CharacterStatus.ALIVE:
            vitals_obj.status = CharacterStatus.DYING
            vitals_obj.dying_final_round = True
            vitals_obj.save(update_fields=["status", "dying_final_round"])
        elif dmg_result.knockout_eligible and vitals_obj.status == CharacterStatus.ALIVE:
            vitals_obj.status = CharacterStatus.UNCONSCIOUS
            vitals_obj.save(update_fields=["status"])

        # Collect condition applications for bulk apply
        if dmg_result.damage_dealt > 0 and conditions:
            target_obj = target_participant.character_sheet.character
            condition_applications.extend((target_obj, ct) for ct in conditions)

    # Bulk-apply all conditions from this NPC action
    if condition_applications:
        from world.conditions.services import bulk_apply_conditions  # noqa: PLC0415

        bulk_apply_conditions(condition_applications)

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


def _check_encounter_completion(encounter: CombatEncounter) -> bool:
    """Return True if the encounter should be marked complete."""
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    all_opponents_down = not CombatOpponent.objects.filter(
        encounter=encounter,
        status=OpponentStatus.ACTIVE,
    ).exists()

    participant_sheet_ids = CombatParticipant.objects.filter(
        encounter=encounter,
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
        "focused_target",
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
    else:
        # Note: round_number is NOT advanced here. begin_declaration_phase
        # handles incrementing round_number when transitioning from
        # BETWEEN_ROUNDS to DECLARING for the next round.
        enc.status = EncounterStatus.BETWEEN_ROUNDS

    enc.save(update_fields=["status"])
    encounter.refresh_from_db()

    return result
