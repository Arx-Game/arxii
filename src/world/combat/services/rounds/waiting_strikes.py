"""The waiting strike: a held melee strike that answers an enemy's approach or attack.

#4608, slice 3 of #4576. A PC declares it (``declare_await_opening``) as the round's one
action. An NPC holds one through a ``WAIT`` move plan (``CombatOpponentMove`` with a
threat entry; selection writes those from slice 4 on). Either fires at most once a round,
from ``fire_waiting_strikes``, which the resolve loop (``_resolve_actions``) calls:

- ``ARRIVED``: after each hop an NPC takes in its slot (``advance_opponent``), any
  waiter whose strike now reaches the mover fires, whether or not the mover attacks.
  PC moves happen at declaration, before any strike is waiting, so only NPC movers
  arrive.
- ``ATTACKING``: before an attack resolves, the waiters among its defenders fire when
  their strike reaches the attacker. Any delivery: a shooter at point-blank draws it, a
  shooter across the room does not. Firing before the attack, not by comparing positions
  before and after, is what catches a blink-strike-blink: the attacker is in reach when
  it strikes even though it ends the action elsewhere.

"Fired" is derived for a PC: the row's ``focused_opponent_target`` is written to the
enemy struck when the strike goes off, and is null until then. An NPC waiter's plan row
carries ``fired``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from world.combat.constants import (
    STOPPED_BEFORE_STRIKING_NARRATION,
    WAITING_STRIKE_LABEL_TAG,
    WAITING_STRIKE_LAPSED_NARRATION,
    WAITING_STRIKE_NARRATION,
    WAITING_STRIKE_NEVER_CAME_NARRATION,
    CombatManeuver,
    OpponentMoveKind,
    OpponentStatus,
    ParticipantStatus,
    WaitingStrikeReason,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatOpponentMove,
    CombatParticipant,
    CombatRoundAction,
)
from world.combat.services.npc.npc_action import _resolve_npc_action
from world.combat.services.techniques.pc_action import resolve_pc_technique
from world.combat.types import ActionOutcome, StrikeResult

if TYPE_CHECKING:
    from world.areas.positioning.models import Position
    from world.checks.models import CheckType
    from world.checks.types import CheckResult

    PerformCheckFn = Callable[..., CheckResult]

Combatant = CombatParticipant | CombatOpponent


def _say(encounter: CombatEncounter, line: str) -> None:
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    broadcast_action_outcome(encounter=encounter, narration=line, target_personas=[])


def combatant_name(combatant: Combatant) -> str:
    """The name the room knows a combatant by: a PC's active persona, an NPC's own name."""
    if isinstance(combatant, CombatOpponent):
        return combatant.name
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    return active_persona_for_sheet(combatant.character_sheet).name


def is_stopped(combatant: Combatant) -> bool:
    """True when ``combatant`` can no longer go on this round (defeated, downed, fled)."""
    if isinstance(combatant, CombatOpponent):
        return combatant.status != OpponentStatus.ACTIVE
    from world.vitals.services import can_act  # noqa: PLC0415

    return combatant.status != ParticipantStatus.ACTIVE or not can_act(combatant.character_sheet)


def _position_of(combatant: Combatant) -> Position | None:
    if isinstance(combatant, CombatOpponent):
        return combatant.current_position if combatant.objectdb is not None else None
    return combatant.current_position


def _hostile_to(waiter: Combatant, mover: Combatant) -> bool:
    from world.combat.services.declarations.hostility import (  # noqa: PLC0415
        combatants_hostile_to,
    )

    hostile = combatants_hostile_to(waiter)
    pool = hostile["opponents"] if isinstance(mover, CombatOpponent) else hostile["participants"]
    return any(c.pk == mover.pk for c in pool)


# ---------------------------------------------------------------------------
# Who is waiting
# ---------------------------------------------------------------------------


def _pc_waiters(encounter: CombatEncounter) -> list[CombatRoundAction]:
    """This round's PC waiting strikes that have not gone off, oldest participant first."""
    return list(
        CombatRoundAction.objects.filter(
            participant__encounter=encounter,
            round_number=encounter.round_number,
            maneuver=CombatManeuver.AWAIT_OPENING,
            focused_opponent_target__isnull=True,
            focused_action__isnull=False,
        )
        .select_related(
            "participant__character_sheet__character",
            "focused_action",
            "focused_action__action_template",
        )
        .order_by("participant_id")
    )


def _npc_waiters(encounter: CombatEncounter) -> list[CombatOpponentMove]:
    """This round's NPC waiting strikes (WAIT plans) that have not gone off."""
    return list(
        CombatOpponentMove.objects.filter(
            opponent__encounter=encounter,
            round_number=encounter.round_number,
            kind=OpponentMoveKind.WAIT,
            fired=False,
        )
        .select_related("opponent", "threat_entry")
        .order_by("opponent_id")
    )


def _pc_waiter_eligible(action: CombatRoundAction, mover: Combatant) -> bool:
    """An ACTIVE PC who can act, hostile to an NPC mover, whose strike reaches it now."""
    from world.combat.reach import technique_can_reach  # noqa: PLC0415

    participant = action.participant
    if not isinstance(mover, CombatOpponent) or is_stopped(participant):
        return False
    if not _hostile_to(participant, mover):
        return False
    if mover.objectdb is None:
        return True  # an unplaced combatant stays lenient
    return technique_can_reach(
        participant.character_sheet.character, action.focused_action, mover.objectdb
    )


def _npc_waiter_eligible(move: CombatOpponentMove, mover: Combatant) -> bool:
    """An ACTIVE opponent hostile to the mover, whose held entry reaches it now."""
    from world.areas.positioning.services import strike_reaches  # noqa: PLC0415

    opponent = move.opponent
    if isinstance(mover, CombatOpponent) and opponent.pk == mover.pk:
        return False
    if is_stopped(opponent) or not _hostile_to(opponent, mover):
        return False
    return strike_reaches(_position_of(opponent), _position_of(mover), move.threat_entry.delivery)


# ---------------------------------------------------------------------------
# Firing
# ---------------------------------------------------------------------------


def _can_pay(action: CombatRoundAction) -> bool:
    """Whether the PC can still pay for the held strike when it fires.

    The cast's only refusal at resolution is the Soulfray checkpoint: with a Soulfray
    stage on, a cast the player did not consent to is not made (``use_technique``).
    Checked here first so a lapsed strike charges nothing, fatigue included.
    """
    from world.magic.services.soulfray import get_soulfray_warning  # noqa: PLC0415

    character = action.participant.character_sheet.character
    return action.confirm_soulfray_risk or get_soulfray_warning(character) is None


def _fire_pc_waiter(
    action: CombatRoundAction,
    mover: CombatOpponent,
    offense_check_fn: PerformCheckFn | None,
) -> ActionOutcome | None:
    """Spend the PC's waiting strike on ``mover``; None when it lapsed unpaid."""
    participant = action.participant
    encounter = participant.encounter
    action.focused_opponent_target = mover
    action.save(update_fields=["focused_opponent_target"])
    name = combatant_name(participant)
    if not _can_pay(action):
        _say(encounter, WAITING_STRIKE_LAPSED_NARRATION.format(name=name))
        return None
    _say(encounter, WAITING_STRIKE_NARRATION.format(name=name, mover=mover.name))
    outcome = resolve_pc_technique(participant, action, offense_check_fn)
    outcome.entity_label = f"{outcome.entity_label} {WAITING_STRIKE_LABEL_TAG}"
    return outcome


def _fire_npc_waiter(
    move: CombatOpponentMove,
    mover: Combatant,
    defense_check_type: CheckType | None,
    defense_check_fn: PerformCheckFn | None,
) -> ActionOutcome:
    """Spend the opponent's held entry on ``mover`` as a real attack row."""
    opponent = move.opponent
    move.fired = True
    move.save(update_fields=["fired"])
    row = CombatOpponentAction.objects.create(
        opponent=opponent,
        round_number=move.round_number,
        threat_entry=move.threat_entry,
    )
    if isinstance(mover, CombatParticipant):
        row.targets.set([mover])
        row.cached_targets = [mover]
        row.cached_opponent_targets = []
    else:
        row.opponent_targets.set([mover])
        row.cached_targets = []
        row.cached_opponent_targets = [mover]
    _say(
        opponent.encounter,
        WAITING_STRIKE_NARRATION.format(name=opponent.name, mover=combatant_name(mover)),
    )
    outcome = _resolve_npc_action(opponent, row, defense_check_type, defense_check_fn)
    outcome.entity_label = f"{outcome.entity_label} {WAITING_STRIKE_LABEL_TAG}"
    return outcome


def fire_waiting_strikes(  # noqa: PLR0913 - the resolve loop's check seams ride along
    encounter: CombatEncounter,
    mover: Combatant,
    *,
    reason: str,
    defenders: Iterable[Combatant] = (),
    offense_check_fn: PerformCheckFn | None = None,
    defense_check_type: CheckType | None = None,
    defense_check_fn: PerformCheckFn | None = None,
    before_fire: Callable[[], None] | None = None,
) -> StrikeResult:
    """Fire every eligible waiting strike at ``mover``; see the module docstring.

    ``reason`` is a ``WaitingStrikeReason``. For ``ATTACKING``, only waiters among
    ``defenders`` (the attack's targets) fire. A waiter is eligible when it is ACTIVE and
    can act, is hostile to the mover, has not fired, and its strike reaches the mover
    from where both stand now. ``before_fire`` runs once, before the first strike (the
    advance uses it to say where the mover stepped before the strike lands).

    When a strike leaves the mover stopped (``is_stopped``), no further waiter fires,
    the room is told "{name} is stopped before striking." and ``mover_stopped`` is True:
    the caller cancels the mover's attack and the rest of its move.
    """
    result = StrikeResult()
    if is_stopped(mover):
        return result
    defender_keys = {(type(d), d.pk) for d in defenders}

    def defends(waiter: Combatant) -> bool:
        return reason != WaitingStrikeReason.ATTACKING or (type(waiter), waiter.pk) in (
            defender_keys
        )

    # PC waiting strikes answer only an NPC mover (a PC's strike is aimed at an opponent).
    pc_rows = (
        [a for a in _pc_waiters(encounter) if defends(a.participant)]
        if isinstance(mover, CombatOpponent)
        else []
    )
    npc_rows = [m for m in _npc_waiters(encounter) if defends(m.opponent)]
    announced = False
    for waiter in [*pc_rows, *npc_rows]:
        eligible = (
            _pc_waiter_eligible(waiter, mover)
            if isinstance(waiter, CombatRoundAction)
            else _npc_waiter_eligible(waiter, mover)
        )
        if not eligible:
            continue
        if before_fire is not None and not announced:
            before_fire()
        announced = True
        if isinstance(waiter, CombatRoundAction) and isinstance(mover, CombatOpponent):
            outcome = _fire_pc_waiter(waiter, mover, offense_check_fn)
        elif isinstance(waiter, CombatOpponentMove):
            outcome = _fire_npc_waiter(waiter, mover, defense_check_type, defense_check_fn)
        else:
            continue
        if outcome is not None:
            result.outcomes.append(outcome)
        if is_stopped(mover):
            result.mover_stopped = True
            _say(encounter, STOPPED_BEFORE_STRIKING_NARRATION.format(name=combatant_name(mover)))
            break
    return result


def narrate_unanswered_waits(encounter: CombatEncounter) -> None:
    """After the resolve loop: "{name} waited for an opening that never came."

    One line per active waiter whose strike never fired this round. It cost them their
    action and nothing else.
    """
    for action in _pc_waiters(encounter):
        if action.participant.status == ParticipantStatus.ACTIVE:
            name = combatant_name(action.participant)
            _say(encounter, WAITING_STRIKE_NEVER_CAME_NARRATION.format(name=name))
    for move in _npc_waiters(encounter):
        if move.opponent.status == OpponentStatus.ACTIVE:
            _say(encounter, WAITING_STRIKE_NEVER_CAME_NARRATION.format(name=move.opponent.name))
