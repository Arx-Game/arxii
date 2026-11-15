"""A PC's round action earns the resonances it feeds (#5124).

The one write seam is ``world.magic.services.kindling.award_kindled_deeds``; this module only
builds the act from the declared action and the live round, once the roll is final.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.round_context import CombatRoundContext
from world.combat.types import CombatTechniqueResolution, CombatTechniqueResult
from world.magic.constants import KindlingActKind
from world.magic.services.kindling import award_kindled_deeds
from world.magic.types.kindling import KindlingAct

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.combat.models import CombatParticipant, CombatRoundAction


def _target_sheet(action: CombatRoundAction) -> CharacterSheet | None:
    """The sheet the action is aimed at: the allied PC, or the opponent's persona's sheet.

    An opponent with no persona has no sheet, so the act has no person to aim at and feeds
    no thread anchor (the other situations still read it).
    """
    ally = action.focused_ally_target
    if ally is not None:
        return ally.character_sheet
    opponent = action.focused_opponent_target
    if opponent is not None and opponent.persona is not None:
        return opponent.persona.character_sheet
    return None


def _technique_check(
    result: CombatTechniqueResult | CombatTechniqueResolution,
) -> CheckResult | None:
    """The cast's check result, from either shape a combat cast returns."""
    if isinstance(result, CombatTechniqueResult):
        use = result.technique_use_result.resolution_result
        return use.check_result if use else None
    return result.check_result


def award_for_technique_cast(
    participant: CombatParticipant,
    action: CombatRoundAction,
    result: CombatTechniqueResult | CombatTechniqueResolution,
) -> None:
    """Earn the resonances a PC's technique cast feeds, scaled by the cast's roll.

    A cast on an ally aids; otherwise it is a technique act on its target.
    """
    check = _technique_check(result)
    if check is None:
        return
    award_kindled_deeds(
        participant.character_sheet,
        act=KindlingAct(
            kind=KindlingActKind.TECHNIQUE,
            target=_target_sheet(action),
            aids=action.focused_ally_target is not None,
        ),
        outcome=check.outcome,
        resolution=CombatRoundContext(participant),
    )


def award_for_strike(
    participant: CombatParticipant, action: CombatRoundAction, hit: CheckResult
) -> None:
    """Earn the resonances a Strike feeds, scaled by its hit roll."""
    award_kindled_deeds(
        participant.character_sheet,
        act=KindlingAct(kind=KindlingActKind.ATTACK, target=_target_sheet(action)),
        outcome=hit.outcome,
        resolution=CombatRoundContext(participant),
    )
