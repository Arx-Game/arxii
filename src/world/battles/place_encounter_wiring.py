"""General party-encounter outcome -> battle auto-wiring (#2008).

Mirrors world.battles.duel_wiring: wires the ENCOUNTER_COMPLETED reactive event to
apply_place_encounter_outcome. When a CombatEncounter bound to a BattlePlace (via
BattlePlace.combat_encounter) completes, the "PC side" — the majority BattleSide
among the BattleParticipants who joined — is credited on VICTORY (the other side's
units at that place rout) or has its own units at that place routed on DEFEAT.
Unlike a Champion duel (a single challenger determines the winner), a party
encounter can have several joiners, so the winning/losing side is the majority
among them, not a single duel_winner FK. FLED/ABANDONED are no-ops — a GM
adjudicates. BattlePlace.controlled_by is never touched here (#2008 Decision 1).
"""

from __future__ import annotations

from collections import Counter
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.battles.models import BattlePlace
    from world.combat.models import CombatEncounter

logger = logging.getLogger(__name__)

PLACE_ENCOUNTER_TRIGGER_NAME = "encounter_completed_place_encounter_outcome"
PLACE_ENCOUNTER_VP_BONUS = 25


def _pc_side_id(battle_place: BattlePlace, encounter: CombatEncounter) -> int | None:
    """Majority BattleSide id among the BattleParticipants who joined *encounter*.

    Returns None when no joiner resolves to a BattleParticipant on this battle
    (e.g. only NPC opponents were added), or when two or more distinct sides tie
    for the maximum join-count — a tie has no majority, so this is a no-op rather
    than a nondeterministic pick.
    """
    from world.battles.models import BattleParticipant  # noqa: PLC0415

    joined_sheet_ids = encounter.participants.values_list("character_sheet_id", flat=True)
    side_ids = BattleParticipant.objects.filter(
        battle=battle_place.battle, character_sheet_id__in=joined_sheet_ids
    ).values_list("side_id", flat=True)
    counts = Counter(side_ids)
    if not counts:
        return None
    top_count = max(counts.values())
    tied_side_ids = [side_id for side_id, count in counts.items() if count == top_count]
    if len(tied_side_ids) > 1:
        return None
    return tied_side_ids[0]


def apply_place_encounter_outcome(*, payload: object) -> None:
    """Flow-callable subscriber for ENCOUNTER_COMPLETED (#2008).

    No-ops cleanly when the completed encounter has no bound BattlePlace, or when
    no joiner resolves to a BattleParticipant. Dispatched by a system-installed
    Trigger (seeded via install_place_encounter_trigger) bound to the seeded
    encounter_completed_place_encounter_outcome TriggerDefinition.
    """
    from world.battles.wiring_helpers import rout_units_at_place  # noqa: PLC0415
    from world.combat.constants import EncounterOutcome, EncounterType  # noqa: PLC0415

    encounter: CombatEncounter = payload.encounter
    if encounter.encounter_type != EncounterType.PARTY_COMBAT:
        # Not a general party encounter (e.g. a Champion duel) — the room-level
        # ENCOUNTER_COMPLETED Trigger fires for every encounter in the battle's
        # shared room, so this handler must ignore encounter types it isn't for
        # (#2008 final-review Critical finding: cross-firing with duel_wiring).
        return

    battle_place = encounter.battle_places.select_related("battle").first()
    if battle_place is None:
        return

    pc_side_id = _pc_side_id(battle_place, encounter)
    if pc_side_id is None:
        return

    if encounter.outcome == EncounterOutcome.VICTORY:
        enemy_sides = battle_place.battle.sides.exclude(pk=pc_side_id)
        for enemy_side in enemy_sides:
            rout_units_at_place(battle_place, side_id=enemy_side.pk)
        side = battle_place.battle.sides.get(pk=pc_side_id)
        side.victory_points += PLACE_ENCOUNTER_VP_BONUS
        side.save(update_fields=["victory_points"])
    elif encounter.outcome == EncounterOutcome.DEFEAT:
        rout_units_at_place(battle_place, side_id=pc_side_id)
    # FLED/ABANDONED: no automatic mechanical effect (#2008 Decision 1).


def install_place_encounter_trigger(encounter: CombatEncounter) -> None:
    """Idempotently install the place-encounter-outcome Trigger on *encounter*'s room.

    Mirrors world.battles.duel_wiring.install_champion_duel_trigger. No-ops when
    the seeded TriggerDefinition is absent (content not wired in this deployment)
    or the encounter has no room.
    """
    from flows.models import Trigger, TriggerDefinition  # noqa: PLC0415

    room = encounter.room
    if room is None:
        return
    trigger_def = TriggerDefinition.objects.filter(name=PLACE_ENCOUNTER_TRIGGER_NAME).first()
    if trigger_def is None:
        return
    trigger, created = Trigger.objects.get_or_create(obj=room, trigger_definition=trigger_def)
    if created:
        handler = getattr(room, "trigger_handler", None)  # noqa: GETATTR_LITERAL
        if handler is not None:
            handler.on_trigger_added(trigger)


def wire_place_encounter_trigger() -> None:
    """Seed the ENCOUNTER_COMPLETED -> place-encounter-outcome TriggerDefinition (idempotent).

    Creates (get_or_create) the encounter_completed_place_encounter_outcome
    FlowDefinition (one CALL_SERVICE_FUNCTION step -> apply_place_encounter_outcome)
    and its TriggerDefinition. Safe to call repeatedly.
    """
    from world.battles.factories import (  # noqa: PLC0415
        BattlePlaceEncounterOutcomeTriggerDefinitionFactory,
    )

    BattlePlaceEncounterOutcomeTriggerDefinitionFactory()
