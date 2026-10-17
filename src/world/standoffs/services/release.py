"""The cause re-test when a Calm or Charmed hold on an opponent ends (#4415, ADR-4415-A).

A hold ending (broken by harm, settled by a player, or lapsed) never starts a fight by
itself (#4091 Decision 21). What it does is take away the one thing keeping the NPC out of
the fight, so the NPC's cause is asked again: does its reason to fight still hold?

- The cause does not hold: the opponent leaves the encounter (FLED) with a room line. A
  group settled by terms has met an Orders, Hunger or Territory cause: they were paid,
  fed or let be, so it does not hold.
- The cause holds, in a standoff (round zero): the opponent's group goes back into the
  standoff and its cause fires as any other would, a proposal for the GM when someone runs
  the scene, the fight beginning (NPC-initiated) when nobody does.
- The cause holds, in a fight already under way: nothing more is needed. The hold is gone,
  so the opponent is hostile again in the next round, as before.

An opponent with no cause, or in an encounter that is over, is left alone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import CauseKind, OpponentStatus
from world.scenes.constants import RoundStatus
from world.standoffs.constants import (
    LINE_RELEASED_LEAVES,
    LIVE_GROUP_STATES,
    REASON_RELEASED,
    StandoffGroupState,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.combat.models import CombatEncounter, CombatOpponent
    from world.standoffs.models import StandoffConfig, StandoffGroup

#: Causes that accepted terms answer: their orders were met, they were fed, they were let be.
TERMS_MEET = frozenset({CauseKind.ORDERS, CauseKind.HUNGER, CauseKind.TERRITORY})


def group_of(opponent: CombatOpponent) -> StandoffGroup:
    """The standoff group the opponent stands in, or an unsaved one shaped like it.

    An encounter that never opened a standoff has no groups; an unsaved group (never
    written) lets the same force and cause tests run on the opponent and its kind.
    """
    from world.standoffs.models import StandoffGroup  # noqa: PLC0415

    lookup = (
        {"persona_id": opponent.persona_id}
        if opponent.persona_id is not None
        else {"creature_template_id": opponent.creature_template_id, "persona__isnull": True}
    )
    group = StandoffGroup.objects.filter(encounter_id=opponent.encounter_id, **lookup).first()
    if group is not None:
        return group
    return StandoffGroup(
        encounter=opponent.encounter,
        creature_template_id=opponent.creature_template_id,
        persona_id=opponent.persona_id,
    )


def release_reason(group: StandoffGroup, config: StandoffConfig) -> str | None:
    """Why the released opponent's cause still holds, or None when it does not."""
    from world.standoffs.services.force import cause_fire_reason  # noqa: PLC0415
    from world.standoffs.services.profile import group_cause  # noqa: PLC0415

    cause, _ = group_cause(group)
    if group.settled_outcome_id is not None and cause in TERMS_MEET:
        return None
    return cause_fire_reason(group, config, released=True)


def retest_cause_on_release(
    target: ObjectDB,  # noqa: OBJECTDB_PARAM - the released NPC body, as the hold names it
) -> None:
    """A hold on ``target`` ended: ask each of its live opponents whether its cause holds.

    Called by ``end_allegiance_with_pool`` and the lapse sweep's plain removal, after the
    condition is gone.
    """
    from world.combat.models import CombatOpponent  # noqa: PLC0415

    opponents = (
        CombatOpponent.objects.filter(objectdb=target, status=OpponentStatus.ACTIVE)
        .exclude(cause=CauseKind.NONE)
        .exclude(encounter__status=RoundStatus.COMPLETED)
        .select_related("encounter")
    )
    for opponent in opponents:
        _retest(opponent)


def _retest(opponent: CombatOpponent) -> None:
    from world.standoffs.models import StandoffConfig  # noqa: PLC0415
    from world.standoffs.services.force import evaluate_causes  # noqa: PLC0415

    encounter = opponent.encounter
    group = group_of(opponent)
    if group.pk is not None and group.state in LIVE_GROUP_STATES:
        # Still in the standoff: its cause is tested as after any other change.
        evaluate_causes(encounter)
        return
    reason = release_reason(group, StandoffConfig.load())
    if reason is None:
        _leave(encounter, opponent)
        return
    if group.pk is not None and group.state == StandoffGroupState.SETTLED:
        _reopen_and_fire(encounter, group, REASON_RELEASED.format(reason=reason))


def _leave(encounter: CombatEncounter, opponent: CombatOpponent) -> None:
    """The NPC has no reason to fight any more: it goes, and the room sees it go."""
    from functools import partial  # noqa: PLC0415

    from django.db import transaction  # noqa: PLC0415

    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    opponent.status = OpponentStatus.FLED
    opponent.save(update_fields=["status"])
    transaction.on_commit(
        partial(
            broadcast_action_outcome,
            encounter=encounter,
            narration=LINE_RELEASED_LEAVES.format(name=opponent.name),
            deliver_telnet=True,
        )
    )


def _reopen_and_fire(encounter: CombatEncounter, group: StandoffGroup, reason: str) -> None:
    """A settled group whose cause holds again is back in the standoff, and its cause fires.

    A GM running the scene gets the proposal (Confirm, Hold, Override) with the reason; with
    nobody running it the fight begins, NPC-initiated, as any firing cause would start it.
    Once round one has begun the group simply rejoins the fight.
    """
    from world.standoffs.services.proposals import propose, standoff_is_gm_run  # noqa: PLC0415
    from world.standoffs.services.state import end_standoff_into_fight  # noqa: PLC0415

    if encounter.round_number != 0:
        # The fight is already under way: the group fights on with the rest.
        group.state = StandoffGroupState.FIGHTING
        group.settled_outcome = None
        group.save(update_fields=["state", "settled_outcome"])
        return
    group.state = StandoffGroupState.OPEN
    group.settled_outcome = None
    group.save(update_fields=["state", "settled_outcome"])
    if standoff_is_gm_run(encounter) and propose(group, reason):
        return
    end_standoff_into_fight(encounter, initiated_by_pc_side=False)
