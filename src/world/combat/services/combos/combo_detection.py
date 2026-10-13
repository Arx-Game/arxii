"""Detecting available combos in a round."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from django.db.models import Prefetch

from world.combat import services as _svc
from world.combat.constants import COMBO_MIN_SLOTS, OpponentStatus, ParticipantStatus
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
from world.combat.services.combos.resolution_order import _fill_slots
from world.combat.types import AvailableCombo, RoundCombo

if TYPE_CHECKING:
    pass


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
