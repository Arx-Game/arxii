"""Declaring a mark."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import OpponentStatus, ParticipantStatus
from world.combat.models import CombatOpponent, CombatParticipant
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.combat.models import CombatMark
    from world.magic.models import Technique


def declare_mark(
    participant: CombatParticipant,
    opponent: CombatOpponent,
    *,
    technique: Technique | None = None,
) -> CombatMark:
    """Declare a mark — a directed, round-scoped combatant reference (#2664).

    A participant declares a target opponent for covenant-mates to focus.
    The mark persists for the round; old marks are ignored (query-scoped by
    ``round_number``). Generic combat primitive — vow content (perks, rungs)
    reads the mark via the ``TARGET_IS_MARKED_BY_ALLY`` situation evaluator.

    Validations mirror ``declare_interpose``: encounter must be in DECLARING
    status, participant must be ACTIVE, opponent must be ACTIVE and in the
    same encounter. Idempotent per round: re-declaring updates the same row.
    """
    from world.combat.models import CombatMark  # noqa: PLC0415
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot mark: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot mark: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot mark: character is dead."
        raise ValueError(msg)

    if opponent.status != OpponentStatus.ACTIVE:
        msg = "Cannot mark a defeated or fled opponent."
        raise ValueError(msg)

    if opponent.encounter_id != encounter.pk:
        msg = "Cannot mark: opponent is not in this encounter."
        raise ValueError(msg)

    mark, _ = CombatMark.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "encounter": encounter,
            "opponent": opponent,
            "source_technique": technique,
        },
    )
    return mark
