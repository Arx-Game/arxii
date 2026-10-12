"""Creating a weakness selection for a cast."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.combat.models import CombatOpponent, CombatParticipant
from world.combat.types import CombatTechniqueResult

if TYPE_CHECKING:
    from world.magic.models import Technique

logger = logging.getLogger(__name__)


def _maybe_create_weakness_selection_for_cast(
    participant: CombatParticipant,
    combat_result: CombatTechniqueResult,
    technique: Technique,
    target_opponent: CombatOpponent | None,
) -> None:
    """Fire the #2665 weakness-reading rider after a successful combat cast.

    Mirrors ``_maybe_produce_insight_for_cast``'s isolation: a weakness-
    reading failure must never break round resolution.
    """
    if not isinstance(combat_result, CombatTechniqueResult):
        return
    if not combat_result.technique_use_result.confirmed:
        return
    try:
        from world.covenants.weakness import maybe_create_weakness_selection  # noqa: PLC0415

        maybe_create_weakness_selection(
            caster_sheet=participant.character_sheet,
            technique=technique,
            resolution_participant=participant,
            target_opponent=target_opponent,
        )
    except Exception:
        logger.exception(
            "Failed to create a weakness selection for a combat cast (participant_id=%s)",
            participant.pk,
        )
