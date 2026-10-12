"""Suggesting an entrance dramatic moment for a cast."""

from __future__ import annotations

import logging

from world.combat.models import CombatParticipant
from world.combat.types import CombatTechniqueResolution, CombatTechniqueResult

logger = logging.getLogger(__name__)


def _maybe_suggest_entrance_dramatic_moment(
    participant: CombatParticipant,
    combat_result: CombatTechniqueResult,
) -> None:
    """Fire the #2183 dramatic-moment suggestion for a resolved entrance-declared cast.

    The combat-round sibling of ``run_entrance_success_hooks``'s suggestion half —
    fired here (not at declaration time) because the real success level is only known
    once the declared cast actually resolves. Best-effort: a suggestion failure must
    never break round resolution.
    """
    if not combat_result.technique_use_result.confirmed:
        return
    resolution = combat_result.technique_use_result.resolution_result
    if not isinstance(resolution, CombatTechniqueResolution):
        return
    try:
        from world.magic.services.gain import maybe_suggest_dramatic_moments  # noqa: PLC0415

        maybe_suggest_dramatic_moments(
            character_sheet=participant.character_sheet,
            scene=participant.encounter.scene,
            success_level=resolution.check_result.success_level,
            interaction=None,
        )
    except Exception:
        logger.exception(
            "Failed to suggest a dramatic moment for entrance-declared cast (participant_id=%s)",
            participant.pk,
        )
