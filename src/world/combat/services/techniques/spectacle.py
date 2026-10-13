"""Applying spectacle for an action."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import SpectacleKind
from world.combat.models import CombatParticipant
from world.combat.services.damage.damage_totals import _opponent_damage_totals
from world.combat.types import ActionOutcome, CombatTechniqueResult

if TYPE_CHECKING:
    from world.magic.models import Technique


def _maybe_apply_spectacle_for_action(
    participant: CombatParticipant,
    technique: Technique,
    combat_result: CombatTechniqueResult | None,
    outcome: ActionOutcome,
    health_before: dict[int, int],
) -> None:
    """Earned displays shake the witnesses (#4147).

    Deliberately unguarded: a failure here is a bug and should fail loudly.
    """
    from world.combat.models import SpectacleConfig  # noqa: PLC0415
    from world.combat.spectacle import (  # noqa: PLC0415
        apply_spectacle,
        classify_cast,
        deliver_spectacle,
        is_devastating,
    )

    config = SpectacleConfig.load()
    kind = None
    success_level = 0
    cast_technique = None
    if isinstance(combat_result, CombatTechniqueResult):
        use = combat_result.technique_use_result
        check = use.resolution_result.check_result if use.resolution_result else None
        success_level = check.success_level if check is not None else 0
        if success_level >= 1:
            kind = classify_cast(
                technique=technique,
                runtime_intensity=use.runtime_intensity,
                success_level=success_level,
                config=config,
            )
            cast_technique = technique
    if kind is None:
        damage = _opponent_damage_totals(outcome)
        if is_devastating(damage_by_opponent=damage, health_before=health_before, config=config):
            kind = SpectacleKind.DEVASTATING_ACTION
    if kind is None:
        return
    result = apply_spectacle(
        encounter=participant.encounter,
        caster_sheet=participant.character_sheet,
        kind=kind,
        display_name=technique.name,
        success_level=success_level,
        technique=cast_technique,
    )
    deliver_spectacle(participant.encounter, result)
