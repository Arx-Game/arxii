"""Producing an insight for a cast."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.combat.models import CombatParticipant
from world.combat.types import CombatTechniqueResult

if TYPE_CHECKING:
    from world.magic.models import Technique

logger = logging.getLogger(__name__)


def _maybe_produce_insight_for_cast(
    participant: CombatParticipant,
    combat_result: CombatTechniqueResult,
    technique: Technique,
) -> None:
    """Fire the #2645 Insight rider after a successful combat cast resolution.

    Mirrors ``_maybe_suggest_entrance_dramatic_moment``'s isolation: an
    Insight failure must never break round resolution. Also mirrors
    ``_record_and_broadcast_pc_action``'s ``isinstance`` guard — only the
    attack path returns a full ``CombatTechniqueResult`` (which carries
    ``technique_use_result``); a routing-isolation test double (or a future
    non-attack path) can hand back a bare ``CombatTechniqueResolution``.
    """
    if not isinstance(combat_result, CombatTechniqueResult):
        return
    if not combat_result.technique_use_result.confirmed:
        return
    try:
        from world.covenants.insight import maybe_produce_insight  # noqa: PLC0415

        maybe_produce_insight(
            caster_sheet=participant.character_sheet,
            technique=technique,
            resolution_participant=participant,
        )
    except Exception:
        logger.exception(
            "Failed to produce an Insight for a combat cast (participant_id=%s)",
            participant.pk,
        )
