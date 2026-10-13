"""Whether combatants are hostile to each other."""

from __future__ import annotations

from world.combat.constants import CombatAllegiance, OpponentStatus, ParticipantStatus
from world.combat.models import CombatOpponent, CombatParticipant
from world.conditions.constants import Allegiance


def combatants_hostile_to(
    actor: CombatParticipant | CombatOpponent,
    *,
    allegiances: dict[int, Allegiance] | None = None,
    opponents: list[CombatOpponent] | None = None,
) -> dict[str, list]:
    """Return the combatants *actor* may attack, grouped by kind (#1584, #4091).

    Reads EFFECTIVE allegiance (stored side composed with allegiance conditions):
    - A PC participant, an ALLY summon or a charmed NPC: hostile to ENEMY and TURNED
      opponents; never to PCs.
    - A TURNED NPC: hostile to other stored-ENEMY opponents still effectively ENEMY.
    - A calmed (NEUTRAL) NPC: hostile to no one.
    - An ENEMY opponent: hostile to PCs and stored ALLY summons only (Decision 3).

    ``opponents`` is the encounter's ACTIVE opponents when the caller already
    holds them (``select_npc_actions`` computes them once per round, #4091 final
    review), so a round with many charmed or turned attackers does not re-query
    them per attacker. Rows are identity-map shared, so one that fled earlier in
    the same pass is dropped by its live status.
    """
    from world.npc_services.allegiance import effective_allegiances  # noqa: PLC0415

    if opponents is None:
        opponents = list(
            CombatOpponent.objects.filter(
                encounter_id=actor.encounter_id, status=OpponentStatus.ACTIVE
            )
        )
    else:
        opponents = [o for o in opponents if o.status == OpponentStatus.ACTIVE]
    if allegiances is None:
        allegiances = effective_allegiances(opponents)
    if isinstance(actor, CombatParticipant):
        side = Allegiance.ALLY_OF_CASTER
    else:
        side = allegiances.get(actor.pk, Allegiance.ENEMY)
    if side == Allegiance.ALLY_OF_CASTER:
        targets = [
            o for o in opponents if allegiances.get(o.pk) in (Allegiance.ENEMY, Allegiance.TURNED)
        ]
        return {"participants": [], "opponents": targets}
    if side == Allegiance.TURNED:
        targets = [
            o
            for o in opponents
            if o.pk != actor.pk
            and o.allegiance == CombatAllegiance.ENEMY
            and allegiances.get(o.pk) == Allegiance.ENEMY
        ]
        return {"participants": [], "opponents": targets}
    if side == Allegiance.NEUTRAL:
        return {"participants": [], "opponents": []}
    active_pcs = list(
        CombatParticipant.objects.filter(
            encounter_id=actor.encounter_id, status=ParticipantStatus.ACTIVE
        )
    )
    allies = [o for o in opponents if o.allegiance == CombatAllegiance.ALLY]
    return {"participants": active_pcs, "opponents": allies}
