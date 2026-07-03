"""Champion duel outcome -> battle auto-wiring (#1710).

Mirrors world.combat.beat_wiring: wires the ENCOUNTER_COMPLETED reactive event
to apply_champion_duel_outcome. When a CombatEncounter bound to a BattlePlace
(via BattlePlace.combat_encounter) completes, the winning side is credited and
the losing side's unit at that front is routed/destroyed.

Champion VICTORY (duel_winner is the challenger's sheet): the enemy unit(s) at
that place are routed (or destroyed if already at low strength) and the
challenger's side is awarded a flat victory-point bonus. Champion DEFEAT
(duel_winner is None — the boss won): the challenger's own side's unit(s) at
that place are routed instead. A still-ongoing or non-battle-bound encounter
is a no-op.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.battles.constants import BattleUnitStatus

if TYPE_CHECKING:
    from world.battles.models import BattlePlace
    from world.combat.models import CombatEncounter

logger = logging.getLogger(__name__)

CHAMPION_DUEL_TRIGGER_NAME = "encounter_completed_champion_duel_outcome"
CHAMPION_DUEL_VP_BONUS = 25


def _rout_units_at_place(battle_place: BattlePlace, *, side_id: int) -> None:
    """Rout (or destroy, if already weak) every ACTIVE unit for *side_id* at *battle_place*.

    Preserves the existing severity rule byte-for-byte — a unit already at or below
    ROUTED_STRENGTH_THRESHOLD is wiped out by a champion's defeat, not merely routed —
    but expresses it through the numeric resources + the shared derivation (#1712)
    instead of writing `status` directly: status must always be a derived view, or a
    later ROUT/RALLY/STRIKE recomputing it for this unit would silently clobber a
    directly-written value.
    """
    from world.battles.constants import ROUTED_STRENGTH_THRESHOLD  # noqa: PLC0415
    from world.battles.models import BattleUnit  # noqa: PLC0415
    from world.battles.resolution import _compute_unit_status  # noqa: PLC0415

    units = BattleUnit.objects.filter(
        place=battle_place, side_id=side_id, status=BattleUnitStatus.ACTIVE
    )
    for unit in units:
        if unit.strength <= ROUTED_STRENGTH_THRESHOLD:
            unit.strength = 0
        unit.morale = 0
        unit.status = _compute_unit_status(unit.strength, unit.morale)
        unit.save(update_fields=["strength", "morale", "status"])


def apply_champion_duel_outcome(*, payload: object) -> None:
    """Flow-callable subscriber for ENCOUNTER_COMPLETED (#1710).

    No-ops cleanly when the completed encounter has no bound BattlePlace (not
    a Champion duel), or — in the defeat/non-victory branch — when no
    BattleParticipant can be resolved at that place. Dispatched by a
    system-installed Trigger (seeded via ``install_champion_duel_trigger``)
    bound to the seeded ``encounter_completed_champion_duel_outcome``
    TriggerDefinition.
    """
    from world.battles.models import BattleParticipant  # noqa: PLC0415

    encounter: CombatEncounter = payload.encounter
    battle_place = encounter.battle_places.select_related("battle").first()
    if battle_place is None:
        return

    challenger = (
        BattleParticipant.objects.filter(
            battle=battle_place.battle, character_sheet_id=encounter.duel_winner_id
        ).first()
        if encounter.duel_winner_id
        else None
    )

    if challenger is not None:
        # Champion victory: rout the enemy unit(s) at this front, credit the side.
        enemy_sides = battle_place.battle.sides.exclude(pk=challenger.side_id)
        for enemy_side in enemy_sides:
            _rout_units_at_place(battle_place, side_id=enemy_side.pk)
        side = challenger.side
        side.victory_points += CHAMPION_DUEL_VP_BONUS
        side.save(update_fields=["victory_points"])
        return

    # Defeat (or fled/abandoned): find who fielded this place's units and rout them.
    # Assumes exactly one PC BattleParticipant per duel place (Champion duels are
    # PC-vs-NPC-boss; no co-located allied PCs today) — .first() is not otherwise
    # ordering-safe.
    any_participant = BattleParticipant.objects.filter(
        battle=battle_place.battle, place=battle_place
    ).first()
    if any_participant is None:
        return
    _rout_units_at_place(battle_place, side_id=any_participant.side_id)


def install_champion_duel_trigger(encounter: CombatEncounter) -> None:
    """Idempotently install the champion-duel-outcome Trigger on *encounter*'s room.

    Mirrors world.combat.beat_wiring.install_encounter_beat_trigger. No-ops
    when the seeded TriggerDefinition is absent (content not wired in this
    deployment) or the encounter has no room.
    """
    from flows.models import Trigger, TriggerDefinition  # noqa: PLC0415

    room = encounter.room
    if room is None:
        return
    trigger_def = TriggerDefinition.objects.filter(name=CHAMPION_DUEL_TRIGGER_NAME).first()
    if trigger_def is None:
        return
    trigger, created = Trigger.objects.get_or_create(obj=room, trigger_definition=trigger_def)
    if created:
        handler = getattr(room, "trigger_handler", None)  # noqa: GETATTR_LITERAL
        if handler is not None:
            handler.on_trigger_added(trigger)


def wire_champion_duel_trigger() -> None:
    """Seed the ENCOUNTER_COMPLETED -> Champion-duel-outcome TriggerDefinition (idempotent).

    Creates (get_or_create) the ``encounter_completed_champion_duel_outcome``
    FlowDefinition (one CALL_SERVICE_FUNCTION step -> apply_champion_duel_outcome)
    and its TriggerDefinition. Safe to call repeatedly.
    """
    from world.battles.factories import (  # noqa: PLC0415
        BattleDuelOutcomeTriggerDefinitionFactory,
    )

    BattleDuelOutcomeTriggerDefinitionFactory()
