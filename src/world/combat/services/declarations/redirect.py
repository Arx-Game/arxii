"""Declaring and routing redirects away from a target."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import OpponentStatus
from world.combat.models import CombatEncounter, CombatOpponent
from world.combat.services.declarations.cover import _combatants_at_position

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models.consequence_pools import ConsequencePool
    from world.areas.positioning.models import Position
    from world.mechanics.models import ObjectProperty


def _validate_redirect_declaration(
    encounter: CombatEncounter,
    redirect_opponent_target: CombatOpponent | None,
    redirect_object_target: ObjectDB | None,  # noqa: OBJECTDB_PARAM
) -> None:
    """Validate a redirect declaration's destination kwargs (#2210).

    Extracted from :func:`declare_interpose` to keep its complexity in check.
    Mutually exclusive; each populated kwarg is validated against the
    encounter it's being declared into. Both ``None`` ("away") needs no
    validation.
    """
    from world.mechanics.services import volatile_object_property  # noqa: PLC0415

    if redirect_opponent_target is not None and redirect_object_target is not None:
        msg = "Cannot interpose: choose at most one redirect destination."
        raise ValueError(msg)

    if redirect_opponent_target is not None and (
        redirect_opponent_target.encounter_id != encounter.pk
        or redirect_opponent_target.status != OpponentStatus.ACTIVE
    ):
        msg = "Redirect target must be an active opponent in this encounter."
        raise ValueError(msg)

    if redirect_object_target is not None:
        if redirect_object_target.db_location_id != encounter.room_id:
            msg = "Redirect target must be an object in the encounter room."
            raise ValueError(msg)
        if volatile_object_property(redirect_object_target) is None:
            msg = "Redirect target is not volatile."
            raise ValueError(msg)


def _redirect_away(
    encounter: CombatEncounter,
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
) -> None:
    """Broadcast the "away" redirect outcome — a silent deflection, no target hit."""
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    narration = f"{interposer.db_key} turns the blow aside — it goes wide, harming no one."
    broadcast_action_outcome(encounter=encounter, narration=narration)


def _redirect_to_object(
    encounter: CombatEncounter,
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
    obj: ObjectDB,  # noqa: OBJECTDB_PARAM
    obj_property: ObjectProperty,
) -> None:
    """Detonate the declared volatile object: fire its pool, consume it, broadcast it.

    Position-anchored only — an object with no ``Position`` (shouldn't happen for
    a volatile object placed in a room with staged positions, but a defensive
    guard) degrades to "away" rather than firing at "everyone in the room."
    """
    from world.areas.positioning.services import position_of  # noqa: PLC0415
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415
    from world.room_features.trap_services import fire_pool_at_characters  # noqa: PLC0415

    position = position_of(obj)
    if position is None:
        _redirect_away(encounter, interposer)
        return

    pool = obj_property.property.detonation.consequence_pool
    opponents = _opponents_at_position(encounter, position)
    opponent_objectdb_ids = {opp.objectdb_id for opp in opponents}
    # PCs only here: a character's damage goes through the sheet-vitals path. Enemies
    # are damaged separately below, through the opponent damage path (#4376).
    characters = [
        c for c in _combatants_at_position(encounter, position) if c.pk not in opponent_objectdb_ids
    ]
    fire_pool_at_characters(pool, characters)
    _detonate_on_opponents(encounter, pool, opponents)
    obj_property.delete()

    narration = f"{interposer.db_key} hurls the blow into {obj.db_key} — it detonates!"
    broadcast_action_outcome(encounter=encounter, narration=narration)


def _opponents_at_position(
    encounter: CombatEncounter,
    position: Position,
) -> list[CombatOpponent]:
    """Every ACTIVE opponent whose objectdb occupies *position*."""
    occupant_ids = set(position.occupants.values_list("objectdb_id", flat=True))
    return [
        opp
        for opp in CombatOpponent.objects.filter(
            encounter=encounter, status=OpponentStatus.ACTIVE
        ).select_related("objectdb")
        if opp.objectdb_id is not None and opp.objectdb_id in occupant_ids
    ]


def _detonate_on_opponents(
    encounter: CombatEncounter,
    pool: ConsequencePool,
    opponents: list[CombatOpponent],
) -> None:
    """Deal each DEAL_DAMAGE effect in *pool* to every opponent, reporting per enemy (#4376).

    An enemy has no character vitals, so the pool's own effect handler cannot reach
    it; each authored damage effect is applied through
    :func:`apply_damage_to_opponent` instead, with the same loop guard as a
    chosen-enemy redirect (``bypass_pre_apply=True``).
    """
    from world.checks.consequence_resolution import resolve_pool_consequences  # noqa: PLC0415
    from world.checks.constants import EffectType  # noqa: PLC0415
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415
    from world.combat.services import apply_damage_to_opponent  # noqa: PLC0415

    damage_effects = [
        effect
        for consequence in resolve_pool_consequences(pool)
        for effect in consequence.effects.filter(effect_type=EffectType.DEAL_DAMAGE)
        if effect.damage_amount and effect.damage_amount > 0
    ]
    for opponent in opponents:
        for effect in damage_effects:
            apply_damage_to_opponent(
                opponent,
                effect.damage_amount,
                bypass_pre_apply=True,
                damage_type=effect.damage_type,
            )
            narration = f"{opponent.name} is caught in the blast for {effect.damage_amount} damage."
            broadcast_action_outcome(encounter=encounter, narration=narration)
