"""Attempting allegiance breaks for an action."""

from __future__ import annotations

from world.combat.constants import OpponentStatus
from world.combat.models import CombatOpponent, CombatParticipant
from world.combat.types import ActionOutcome


def _attempt_allegiance_breaks_for_action(
    participant: CombatParticipant, outcome: ActionOutcome
) -> None:
    """#4091 Decision 16, fix round 1: one break-attempt roll per opponent per PC
    action, not per damage call.

    ``outcome.damage_results`` at the point this is called (from
    ``_resolve_pc_action``, right after the technique pipeline AND any combo
    rider have both run, before the wind-up interception rider) holds every
    ``OpponentDamageResult`` this single PC action produced — every damage
    profile against every target, plus the combo rider's own hit. Grouping by
    ``opponent_id`` and summing ``damage_dealt`` gives the blow's TOTAL pressure
    against each opponent it actually harmed, so a multi-profile technique or a
    combo-upgraded hit rolls exactly once per opponent, against the combined
    damage -- never once per profile (previously inside ``apply_damage_to_opponent``
    itself, which fired, and narrated a "holds" line, on every single profile/
    rider call).

    Only a PC's own chosen strike reaches here (this function is called only
    from ``_resolve_pc_action``) -- NPC-vs-NPC (``_resolve_npc_action_on_opponent_
    target``), reflected, rampart, and duel-mirror damage never do.
    """
    from world.npc_services.allegiance import (  # noqa: PLC0415
        allegiance_instances_for,
        designating_instance,
    )
    from world.npc_services.allegiance_outcomes import attempt_allegiance_break  # noqa: PLC0415

    totals: dict[int, int] = {}
    for result in outcome.damage_results:
        opponent_id = result.opponent_id
        if opponent_id is None or result.damage_dealt <= 0:
            continue
        totals[opponent_id] = totals.get(opponent_id, 0) + result.damage_dealt
    if not totals:
        return

    # Batched (#4091 final review): one opponent fetch and one allegiance-instance
    # fetch for every harmed opponent, not a SELECT plus get_active_conditions each.
    opponents = [
        opponent
        for opponent in CombatOpponent.objects.filter(pk__in=totals)
        .exclude(status=OpponentStatus.DEFEATED)
        .select_related("objectdb")
        .order_by("pk")
        if opponent.objectdb_id is not None
    ]
    by_target = allegiance_instances_for(o.objectdb_id for o in opponents)
    for opponent in opponents:
        instance = designating_instance(by_target.get(opponent.objectdb_id, []))
        if instance is None:
            continue
        attempt_allegiance_break(
            striker=participant.character_sheet,
            opponent=opponent,
            damage_dealt=totals[opponent.pk],
            instance=instance,
        )
