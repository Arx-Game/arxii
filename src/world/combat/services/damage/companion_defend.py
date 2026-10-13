"""Companion defend and the on-hit pool."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flows.events.payloads import DamagePreApplyPayload
from world.combat import services as _svc
from world.combat.constants import OpponentStatus
from world.combat.models import CombatOpponent, CombatParticipant
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from actions.models.consequence_pools import ConsequencePool
    from typeclasses.characters import Character


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
    _svc.apply_damage_to_opponent(
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
