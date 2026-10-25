"""Classifying and broadcasting an encounter's outcome."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from flows.constants import EventName
from flows.events.payloads import EncounterCompletedPayload
from world.combat import services as _svc
from world.combat.constants import (
    CombatAllegiance,
    EncounterOutcome,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
)
from world.combat.models import CombatEncounter, CombatOpponent, CombatParticipant

if TYPE_CHECKING:
    from world.scenes.models import Interaction

logger = logging.getLogger(__name__)


def _classify_encounter_outcome(encounter: CombatEncounter) -> EncounterOutcome:
    """Classify a completing encounter (#876 spec §1).

    1. No ACTIVE opponents and no Hero Killer present → VICTORY. An unbeatable
       Hero Killer (#875) still ACTIVE and still hostile forbids VICTORY — but
       a Hero Killer won over (charmed/turned/calmed) counts as won over like
       any other enemy: social victory ends the fight too (#4091 fix round 2).
       A FLED (or otherwise non-ACTIVE) Hero Killer keeps the original "at any
       status forbids VICTORY" behavior.
    2. No ACTIVE participants and at least one FLED → FLED.
    3. Else → DEFEAT (catch-all: downed ACTIVE participants, or all-REMOVED).
    """
    # VICTORY hinges on ENEMY opponents only — an ALLY summon left standing is
    # part of the winning side, not a reason to withhold victory (#1584). A
    # won-over enemy (charmed, turned, calmed during THIS encounter — ruling
    # R1) does not count as hostile either (#4091).
    from world.combat.won_over import hostile_opponents_remain  # noqa: PLC0415

    any_active_opponents = hostile_opponents_remain(encounter)
    if not any_active_opponents:
        # Reaching this branch already proves no ACTIVE+stored-ENEMY opponent
        # (Hero Killer included) is still effectively hostile -- hostile_opponents_remain
        # just said so. So an ACTIVE Hero Killer found here is, by construction, won
        # over; exclude it from "present" (#4091 fix round 2). A FLED/DEFEATED/REMOVED
        # Hero Killer is untouched by that guarantee and still blocks VICTORY.
        hero_killer_present = (
            CombatOpponent.objects.filter(encounter=encounter, tier=OpponentTier.HERO_KILLER)
            .exclude(status=OpponentStatus.ACTIVE)
            .exists()
        )
        if not hero_killer_present:
            return EncounterOutcome.VICTORY
        # An unbeatable Hero Killer was on the field -- never a victory.
        # Fall through to FLED / DEFEAT classification below.

    statuses = set(
        CombatParticipant.objects.filter(encounter=encounter).values_list("status", flat=True)
    )
    no_active = ParticipantStatus.ACTIVE not in statuses
    if no_active and ParticipantStatus.FLED in statuses:
        return EncounterOutcome.FLED
    return EncounterOutcome.DEFEAT


def _broadcast_encounter_outcome(
    encounter: CombatEncounter, outcome: EncounterOutcome
) -> Interaction | None:
    """Assemble side labels and persist+broadcast the ceremonial OUTCOME line."""
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        render_encounter_outcome_narration,
    )
    from world.combat.won_over import won_over_labels  # noqa: PLC0415
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    participants = list(
        CombatParticipant.objects.filter(encounter=encounter).select_related(
            "character_sheet__character"
        )
    )
    opponents = list(CombatOpponent.objects.filter(encounter=encounter))
    # Persona display name, not str(CombatParticipant) -> str(CharacterSheet)
    # ("Sheet for {key}") -- a player-facing line shows the face the character
    # is CURRENTLY presenting as, batched in one call (#4091 fix round 2).
    persona_names = persona_names_for_sheets(p.character_sheet_id for p in participants)

    def _label(participant: CombatParticipant) -> str:
        return persona_names.get(
            participant.character_sheet_id, participant.character_sheet.character.key
        )

    narration = render_encounter_outcome_narration(
        outcome=outcome,
        active_labels=[_label(p) for p in participants if p.status == ParticipantStatus.ACTIVE],
        fled_labels=[_label(p) for p in participants if p.status == ParticipantStatus.FLED],
        defeated_opponent_labels=[
            o.name
            for o in opponents
            if o.status == OpponentStatus.DEFEATED and o.allegiance == CombatAllegiance.ENEMY
        ],
        won_over=[(name, verb) for name, verb, _src in won_over_labels(encounter)],
    )
    return broadcast_action_outcome(encounter=encounter, narration=narration)


def _emit_encounter_completed(encounter: CombatEncounter, outcome: EncounterOutcome) -> None:
    """Emit the ENCOUNTER_COMPLETED reactive hook (#876 §6).

    Downstream systems — stories, missions, achievements, Legend — subscribe
    via triggers. Never XP: combat does not award XP. Skips when no room
    (emit_event requires a location); mirrors the _emit_death_gate idiom.
    """
    room = encounter.room
    if room is None:
        logger.debug(
            "Encounter %s completed with no room; skipping ENCOUNTER_COMPLETED emit.",
            encounter.pk,
        )
        return
    _svc.emit_event(
        EventName.ENCOUNTER_COMPLETED,
        EncounterCompletedPayload(
            encounter=encounter,
            outcome=str(outcome),
            scene=encounter.scene,
            room=room,
        ),
        location=room,
    )
