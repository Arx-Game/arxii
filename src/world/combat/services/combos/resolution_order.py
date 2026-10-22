"""Ordering actions for resolution and matching combo slots."""

from __future__ import annotations

from collections.abc import Iterable

from world.combat.constants import (
    ENTITY_TYPE_NPC,
    ENTITY_TYPE_PC,
    NO_ROLE_SPEED_RANK,
    NPC_SPEED_RANK,
    OpponentStatus,
    ParticipantStatus,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
    ComboSlot,
)
from world.combat.types import ComboSlotFill, ComboSlotMatch
from world.conditions.services import turn_order_modifier_by_target


def effective_speed_ranks(
    participants: Iterable[CombatParticipant],
    opponents: Iterable[CombatOpponent] = (),
) -> dict[tuple[str, int], int]:
    """Effective speed rank per combatant, keyed ``(entity_type, pk)`` (#4572).

    The one place round order is decided: ``get_resolution_order`` and the encounter
    serializer's initiative chips both sort on it, so they cannot disagree. Base rank
    is the PC's covenant role speed (NO_ROLE_SPEED_RANK when none) or NPC_SPEED_RANK;
    the bearer's summed active turn order modifier is subtracted, so a positive
    modifier acts earlier (lower rank). One conditions query covers the whole batch.
    Participants need ``covenant_role`` and ``character_sheet__character`` loaded;
    an opponent with no ObjectDB cannot bear conditions and keeps its base rank.
    """
    participants = list(participants)
    opponents = list(opponents)
    bearers = [p.character_sheet.character for p in participants]
    bearers.extend(o.objectdb for o in opponents if o.objectdb_id is not None)
    modifiers = turn_order_modifier_by_target(bearers)

    ranks: dict[tuple[str, int], int] = {}
    for p in participants:
        base = p.covenant_role.speed_rank if p.covenant_role_id else NO_ROLE_SPEED_RANK
        ranks[(ENTITY_TYPE_PC, p.pk)] = base - modifiers.get(p.character_sheet.character.pk, 0)
    for o in opponents:
        shift = modifiers.get(o.objectdb_id, 0) if o.objectdb_id is not None else 0
        ranks[(ENTITY_TYPE_NPC, o.pk)] = NPC_SPEED_RANK - shift
    return ranks


def get_resolution_order(
    encounter: CombatEncounter,
) -> list[tuple[str, CombatParticipant | CombatOpponent]]:
    """Build the resolution order for a combat round.

    Returns a sorted list of (entity_type, entity) tuples where entity_type
    is "pc" or "npc". Sorted by effective speed rank ascending (lower = faster),
    see ``effective_speed_ranks`` (turn order conditions shift a combatant's rank).

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

    actors = [p for p in participants if can_act(p.character_sheet)]
    opponents = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
        ).select_related("objectdb")
    )
    ranks = effective_speed_ranks(actors, opponents)

    ranked: list[tuple[str, CombatParticipant | CombatOpponent]] = [
        (ENTITY_TYPE_PC, p) for p in actors
    ]
    ranked.extend((ENTITY_TYPE_NPC, o) for o in opponents)
    ranked.sort(key=lambda item: (ranks[(item[0], item[1].pk)], item[1].pk))
    return ranked


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
