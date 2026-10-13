"""Interpose and reactive challenges that gate a reaction."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.combat.constants import (
    CombatAllegiance,
    CombatManeuver,
    OpponentStatus,
    ParticipantStatus,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

logger = logging.getLogger(__name__)


def _bind_interpose_challenges_any_ally(
    template: object,
    room: object,
    interposer_participant_id: int,
    active_participants_by_id: dict[int, CombatParticipant],
    active_ally_opponent_objectdbs: list[ObjectDB],
) -> None:
    """Bind a ChallengeInstance to every active participant and ALLY opponent.

    Every active participant except the interposer, plus every ALLY-allegiance
    ``CombatOpponent``'s objectdb (player summons/companion NPCs, #2207) — so a
    mundane guardian's :func:`dispatch_capability_reaction` finds a bound
    challenge instance when shielding a summon via the ANY-ALLY path. Note: this
    is the ONLY path that can bind a summon-ward — ``focused_ally_target`` FKs
    ``CombatParticipant``, so a summon can never be named as a *specific* ward
    (named-ally guarding of a summon is a follow-up).
    """
    from world.mechanics.models import ChallengeInstance  # noqa: PLC0415

    for part_id, part in active_participants_by_id.items():
        if part_id == interposer_participant_id:
            continue
        ally_char = part.character_sheet.character
        ChallengeInstance.objects.get_or_create(
            template=template,
            target_object=ally_char,
            is_active=True,
            defaults={"location": room, "is_revealed": True},
        )

    for ally_objectdb in active_ally_opponent_objectdbs:
        ChallengeInstance.objects.get_or_create(
            template=template,
            target_object=ally_objectdb,
            is_active=True,
            defaults={"location": room, "is_revealed": True},
        )


def _ensure_interpose_challenges(
    encounter: CombatEncounter,
    pc_actions: dict[int, CombatRoundAction],
) -> None:
    """Round pre-pass: bind an Interpose ChallengeInstance to each protected ally.

    For every armed INTERPOSE ``CombatRoundAction`` this round, idempotently
    ``get_or_create`` an active+revealed ``ChallengeInstance`` from the seeded
    Interpose ``ChallengeTemplate`` bound to each protected ally's character
    ObjectDB (``target_object``), so ``get_available_actions(interposer, room)``
    can surface the approach.

    - Specific-ally path (``focused_ally_target`` set): binds to that ally's character.
    - Any-ally path (``focused_ally_target=None``): binds to every ACTIVE participant
      in this encounter except the interposer, plus every ACTIVE ALLY-allegiance
      ``CombatOpponent``'s objectdb (a summon/companion NPC, #2207) — the only path
      that can bind a summon-ward, since ``focused_ally_target`` FKs
      ``CombatParticipant`` and so cannot name a specific opponent.

    Idempotent: ``get_or_create`` on (template, target_object, is_active=True) ensures
    no duplicates when called multiple times in the same round.

    No queries in loops: the active-ally list is fetched once per any-ally action;
    the template is fetched once before the loop.
    """
    from world.mechanics.models import ChallengeInstance, ChallengeTemplate  # noqa: PLC0415

    # Collect armed interpose actions for this round.
    interpose_actions = [
        action
        for action in pc_actions.values()
        if action.maneuver == CombatManeuver.INTERPOSE and action.is_ready
    ]
    if not interpose_actions:
        return

    try:
        template = ChallengeTemplate.objects.get(name="Interpose")
    except ChallengeTemplate.DoesNotExist:
        logger.warning(
            "Interpose ChallengeTemplate not seeded; skipping challenge binding for encounter %s.",
            encounter.pk,
        )
        return

    room = encounter.room

    # Fetch all active allies once (needed for the any-ally path).
    # select_related prevents N+1 when accessing .character_sheet.character below.
    active_participants_by_id: dict[int, CombatParticipant] | None = None
    # Fetch active ALLY-allegiance opponents (summons/companion NPCs) once too,
    # for the same any-ally path (#2207).
    active_ally_opponent_objectdbs: list[ObjectDB] | None = None

    for action in interpose_actions:
        interposer_participant_id = action.participant_id

        if action.focused_ally_target_id is not None:
            # Specific-ally path: bind to the declared ally's character.
            ally_char = action.focused_ally_target.character_sheet.character
            ChallengeInstance.objects.get_or_create(
                template=template,
                target_object=ally_char,
                is_active=True,
                defaults={"location": room, "is_revealed": True},
            )
        else:
            # Any-ally path: bind to every active participant except the interposer,
            # plus every active ALLY-allegiance opponent (summon/companion NPC, #2207).
            if active_participants_by_id is None:
                active_participants_by_id = {
                    p.pk: p
                    for p in CombatParticipant.objects.filter(
                        encounter=encounter,
                        status=ParticipantStatus.ACTIVE,
                    ).select_related("character_sheet__character")
                }
            if active_ally_opponent_objectdbs is None:
                active_ally_opponent_objectdbs = [
                    opp.objectdb
                    for opp in CombatOpponent.objects.filter(
                        encounter=encounter,
                        status=OpponentStatus.ACTIVE,
                        allegiance=CombatAllegiance.ALLY,
                    ).select_related("objectdb")
                    if opp.objectdb is not None
                ]
            _bind_interpose_challenges_any_ally(
                template,
                room,
                interposer_participant_id,
                active_participants_by_id,
                active_ally_opponent_objectdbs,
            )


def _ensure_succor_challenges(
    encounter: CombatEncounter,
    pc_actions: dict[int, CombatRoundAction],
) -> None:
    """Round pre-pass: bind a Succor ChallengeInstance to each protected ally.

    Mirrors _ensure_interpose_challenges but Succor always names a specific ally
    (no "any ally" path — see declare_succor's docstring).
    """
    from world.mechanics.models import ChallengeInstance, ChallengeTemplate  # noqa: PLC0415

    succor_actions = [
        action
        for action in pc_actions.values()
        if action.maneuver == CombatManeuver.SUCCOR and action.is_ready
    ]
    if not succor_actions:
        return

    from world.combat.succor_content import SUCCOR_CHALLENGE_NAME  # noqa: PLC0415

    try:
        template = ChallengeTemplate.objects.get(name=SUCCOR_CHALLENGE_NAME)
    except ChallengeTemplate.DoesNotExist:
        logger.warning(
            "Succor ChallengeTemplate not seeded; skipping challenge binding for encounter %s.",
            encounter.pk,
        )
        return

    room = encounter.room
    for action in succor_actions:
        ally_char = action.focused_ally_target.character_sheet.character
        ChallengeInstance.objects.get_or_create(
            template=template,
            target_object=ally_char,
            is_active=True,
            defaults={"location": room, "is_revealed": True},
        )


def _ensure_reactive_challenges(
    encounter: CombatEncounter,
    pc_actions: dict[int, CombatRoundAction],
) -> None:
    """Round pre-pass: bind both Interpose and Succor challenge instances.

    A single call site for ``resolve_round`` (#1273, #1744) — keeps the two
    independent reactive-challenge binders (blow vs. hazard) from adding a
    second statement to an already-large function.
    """
    _ensure_interpose_challenges(encounter, pc_actions)
    _ensure_succor_challenges(encounter, pc_actions)
