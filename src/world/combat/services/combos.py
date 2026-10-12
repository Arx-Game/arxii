"""Round combos: detection, slot matching, upgrades, and outcomes."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from django.db.models import Prefetch, Sum

from flows.constants import EventName
from flows.events.payloads import CharacterIncapacitatedPayload, DamageAppliedPayload
from world.combat import services as _svc
from world.combat.constants import (
    COMBO_MIN_SLOTS,
    ENTITY_TYPE_NPC,
    ENTITY_TYPE_PC,
    NO_ROLE_SPEED_RANK,
    NPC_SPEED_RANK,
    OpponentStatus,
    ParticipantStatus,
)
from world.combat.models import (
    Clash,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
    ComboDefinition,
    ComboLearning,
    ComboSlot,
)
from world.combat.services.foundations import _emit_death_gate
from world.combat.types import (
    ActionOutcome,
    AvailableCombo,
    ComboSlotFill,
    ComboSlotMatch,
    RoundCombo,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from flows.events.payloads import DamageSource
    from typeclasses.characters import Character
    from world.conditions.models import DamageType


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
    _svc.emit_event(EventName.DAMAGE_APPLIED, applied_payload, location=room)

    will_emit_death_gate = death_eligible or force_death
    if knockout_eligible and not was_in_knockout_band and not will_emit_death_gate:
        _svc.emit_event(
            EventName.CHARACTER_INCAPACITATED,
            CharacterIncapacitatedPayload(
                character=character,
                source_event=EventName.DAMAGE_PRE_APPLY,
            ),
            location=room,
        )
    if will_emit_death_gate:
        _emit_death_gate(character, room)


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
    if slot.required_archetype and not _participant_has_archetype(
        action.participant, slot.required_archetype
    ):
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


def _unused_matches(
    slot: ComboSlot,
    actions: list[CombatRoundAction],
    assignment: dict[int, CombatRoundAction],
    gift_resonance_ids: dict[int, set[int]],
) -> list[CombatRoundAction]:
    """Actions not yet assigned to a slot that satisfy ``slot``."""
    used_action_ids = {action.pk for action in assignment.values()}
    return [
        action
        for action in actions
        if action.pk not in used_action_ids
        and _action_matches_slot(action, slot, gift_resonance_ids)
    ]


def _best_slot_assignment(
    slots: list[ComboSlot],
    actions: list[CombatRoundAction],
    gift_resonance_ids: dict[int, set[int]],
) -> dict[int, CombatRoundAction]:
    """Assign distinct actions to slots, filling as many slots as possible.

    Backtracking over "this action fills the slot" and "the slot stays open"
    keeps matching order-independent for combos with 2-5 slots, and the
    fullest assignment wins, so a party sees the true number of open slots
    (#3553) and a complete fill is found whenever one exists. Keyed by slot pk.
    """
    assignment: dict[int, CombatRoundAction] = {}
    best: dict[int, CombatRoundAction] = {}

    def backtrack(slot_idx: int) -> None:
        nonlocal best
        if len(best) == len(slots):
            return
        if slot_idx >= len(slots):
            if len(assignment) > len(best):
                best = dict(assignment)
            return
        slot = slots[slot_idx]
        for action in _unused_matches(slot, actions, assignment, gift_resonance_ids):
            assignment[slot.pk] = action
            backtrack(slot_idx + 1)
            del assignment[slot.pk]
        backtrack(slot_idx + 1)

    backtrack(0)
    return best


def _fill_slots(
    slots: list[ComboSlot],
    actions: list[CombatRoundAction],
    gift_resonance_ids: dict[int, set[int]],
) -> list[ComboSlotFill]:
    """One ``ComboSlotFill`` per slot, in slot order, from the fullest assignment."""
    # #2051 invariant: combos are never solo — each slot must be filled by a
    # distinct PC-controlled action. CombatRoundAction requires a
    # CombatParticipant (PC) FK; companions materialize as CombatOpponent and
    # cannot produce one. This filter is defense-in-depth against future
    # companion-action surfaces.
    pc_actions = [a for a in actions if a.participant_id is not None]
    best = _best_slot_assignment(slots, pc_actions, gift_resonance_ids)

    fills: list[ComboSlotFill] = []
    for slot in slots:
        action = best.get(slot.pk)
        match = (
            None
            if action is None
            else ComboSlotMatch(
                slot_number=slot.slot_number,
                participant=action.participant,
                action=action,
            )
        )
        fills.append(ComboSlotFill(slot=slot, match=match))
    return fills


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


def _build_round_combo(  # noqa: PLR0913 - prefetched availability inputs
    combo: ComboDefinition,
    *,
    actions: list[CombatRoundAction],
    gift_resonance_ids: dict[int, set[int]],
    known_map: dict[int, set[int]],
    participant_sheet_ids: set[int],
    max_probing: int,
    encounter_clash_flavors: set[str],
    active_window_condition_template_ids: set[int],
) -> RoundCombo | None:
    """Return the ``RoundCombo`` for ``combo`` if it is taking shape this round, else None.

    Applies the availability gates in order: slots present, minimum probing,
    known-or-discoverable, clash-state prerequisites, then slot filling. A
    partial fill is returned only for a combo a PC in the encounter knows
    (#3553); an unknown, discoverable combo surfaces only once it is complete.
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

    # Backtracking slot filling: each slot is filled by a distinct action, or open.
    slot_fills = _fill_slots(slots, actions, gift_resonance_ids)
    round_combo = RoundCombo(
        combo=combo,
        slot_fills=slot_fills,
        known_by_participant=known_by_any,
    )
    if round_combo.filled_count == 0:
        return None
    if not round_combo.complete and not known_by_any:
        return None
    return round_combo


def scan_round_combos(
    encounter: CombatEncounter,
    round_number: int,
) -> list[RoundCombo]:
    """List every combo taking shape in this round's declared actions (#3553).

    A combo is listed, with each slot marked filled or open, when:
    - At least one slot is filled by a participant's focused action, and every
      slot is filled by a distinct participant's action.
    - The combo's ``minimum_probing`` (if set) is met by at least one active
      opponent in the encounter.
    - A PC in the encounter knows the combo (``ComboLearning``), **or** the
      combo is ``discoverable_via_combat`` and every slot is filled. Knowledge
      counts before the knower declares, so a party can see "one more Attack
      completes Pincer" while the round is still open; an unknown combo is
      never hinted at.
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
        List of ``RoundCombo`` instances, one per combo, each with a
        slot-by-slot fill.
    """
    actions = list(
        CombatRoundAction.objects.filter(
            participant__encounter=encounter,
            round_number=round_number,
            focused_action__isnull=False,
        ).select_related(
            "participant",
            "participant__character_sheet",
            "participant__character_sheet__character",
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
                    "resonance_requirement",
                ).order_by("slot_number"),
                to_attr="cached_slots",
            ),
        )
    )

    # Pre-fetch which characters know which combos (one query). Every active
    # PC in the encounter counts, declared or not (#3553).
    participant_sheet_ids = set(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        ).values_list("character_sheet_id", flat=True)
    )
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

    round_combos: list[RoundCombo] = []

    for combo in combos:
        result = _build_round_combo(
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
            round_combos.append(result)

    return round_combos


def detect_available_combos(
    encounter: CombatEncounter,
    round_number: int,
) -> list[AvailableCombo]:
    """Scan declared actions to find combos whose slots are all satisfied.

    The complete fills from ``scan_round_combos``; see it for the gates.

    Returns:
        List of ``AvailableCombo`` instances with slot→participant mappings.
    """
    return [
        rc.as_available() for rc in _svc.scan_round_combos(encounter, round_number) if rc.complete
    ]


def _combo_composition_is_eligible(
    available: AvailableCombo,
) -> bool:
    """Return whether every current combo contributor can still act.

    Combo scanning describes declared techniques.  A contributor can become
    dead or unconscious after declaring, so the upgrade and resolution gates
    also check the live agency state.
    """
    from world.vitals.services import can_act  # noqa: PLC0415

    return all(
        match.participant.status == ParticipantStatus.ACTIVE
        and can_act(match.participant.character_sheet)
        for match in available.slot_matches
    )


def _available_combo_for_action(
    action: CombatRoundAction,
    combo: ComboDefinition,
) -> AvailableCombo | None:
    """Find a complete scanned combo that includes *action*, if one exists."""
    encounter = action.participant.encounter
    for available in detect_available_combos(encounter, action.round_number):
        if available.combo.pk != combo.pk:
            continue
        if any(match.action.pk == action.pk for match in available.slot_matches):
            return available if _combo_composition_is_eligible(available) else None
    return None


def _revalidate_combo_upgrades(
    encounter: CombatEncounter,
    round_number: int,
    actions: dict[int, CombatRoundAction],
) -> None:
    """Clear upgrades whose complete composition is no longer valid.

    This is deliberately done after all declarations and late auto-declarations
    are loaded, rather than trusting the declaration-time upgrade.  Changed
    targets, removed contributors, and lost agency therefore cannot grant a
    combo rider at resolution.
    """
    available = {item.combo.pk: item for item in detect_available_combos(encounter, round_number)}
    for action in actions.values():
        combo_id = action.combo_upgrade_id
        if combo_id is None:
            continue
        candidate = available.get(combo_id)
        valid = False
        if candidate is not None:
            valid = any(match.action.pk == action.pk for match in candidate.slot_matches)
            if valid:
                valid = _combo_composition_is_eligible(candidate)
        if not valid:
            action.combo_upgrade = None
            action.save(update_fields=["combo_upgrade_id"])


def upgrade_action_to_combo(
    action: CombatRoundAction,
    combo: ComboDefinition,
) -> None:
    """Mark a currently eligible PC action as upgraded to a combo.

    The scanner is the authoritative source for slot matching.  Callers get a
    ``ValueError`` instead of being able to persist an arbitrary combo FK.

    Args:
        action: The CombatRoundAction to upgrade.
        combo: The ComboDefinition being activated.

    Raises:
        ValueError: If the current team declarations do not complete *combo*.
    """
    if _available_combo_for_action(action, combo) is None:
        msg = "Combo is not available for this declared action."
        raise ValueError(msg)
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


def _group_combo_outcomes(
    action_outcomes: list[ActionOutcome],
) -> dict[int, list[tuple[ActionOutcome, CombatParticipant]]]:
    """Group ``action_outcomes`` by ``combo_used``, resolving each participant.

    Extracted from ``_process_combo_outcomes`` (S3776) — same grouping pass,
    same behavior, just named on its own.
    """
    combo_groups: dict[int, list[tuple[ActionOutcome, CombatParticipant]]] = defaultdict(list)
    for outcome in action_outcomes:
        if outcome.combo_used is not None and outcome.participant_id is not None:
            participant = (
                CombatParticipant.objects.filter(pk=outcome.participant_id)
                .select_related("character_sheet__character")
                .first()
            )
            if participant is not None:
                combo_groups[outcome.combo_used.pk].append((outcome, participant))
    return combo_groups


def _broadcast_combo_finisher_narration(
    combo: ComboDefinition,
    group: list[tuple[ActionOutcome, CombatParticipant]],
    round_number: int,
    encounter: CombatEncounter,
) -> None:
    """Broadcast the joint finisher narration for one multi-contributor combo group.

    Extracted from ``_process_combo_outcomes`` (S3776) — same target-label
    lookup and narration/broadcast calls, same behavior, just named on its
    own.
    """
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        render_combo_finisher_narration,
    )
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    # Persona display name, not str(CombatParticipant) -> str(CharacterSheet)
    # ("Sheet for {key}") -- #4091 fix round 3.
    persona_names = persona_names_for_sheets(p.character_sheet_id for _, p in group)
    contributor_labels = [
        persona_names.get(p.character_sheet_id, p.character_sheet.character.key) for _, p in group
    ]
    total_damage = sum(dr.damage_dealt for outcome, _ in group for dr in outcome.damage_results)
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
