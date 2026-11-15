"""A PC's round action earns the resonances it feeds (#5124).

The one write seam is ``world.magic.services.kindling.award_kindled_deeds``. This module
builds the act from the declared action and the live round, in one place, so every resolver
earns through one line: ``award_rolled`` for an act that rolled a check, ``award_unrolled``
for one that rolled nothing of its own (it earns at the plainest success).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.round_context import CombatRoundContext
from world.combat.types import CombatTechniqueResolution, CombatTechniqueResult
from world.magic.constants import KindlingActKind
from world.magic.services.kindling import (
    active_mission_for,
    award_kindled_deeds,
    lowest_success_outcome,
)
from world.magic.types.kindling import KindlingAct

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.combat.models import CombatOpponent, CombatParticipant, CombatRoundAction
    from world.traits.models import CheckOutcome


def target_sheet(action: CombatRoundAction) -> CharacterSheet | None:
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


def award_rolled(  # noqa: PLR0913 - the act's kind, who it was aimed at and what it rolled
    participant: CombatParticipant,
    action: CombatRoundAction | None,
    *,
    kind: str,
    outcome: CheckOutcome | None,
    target: CharacterSheet | None = None,
    aids: bool = False,
) -> None:
    """Earn what a PC's act feeds, scaled by the ``outcome`` of the roll it made.

    ``target`` defaults to the person ``action`` is aimed at. A failed roll earns by its own
    outcome row (normally none).
    """
    award_kindled_deeds(
        participant.character_sheet,
        act=KindlingAct(
            kind=kind,
            target=target if target is not None else (target_sheet(action) if action else None),
            aids=aids,
        ),
        outcome=outcome,
        resolution=CombatRoundContext(participant),
        mission=active_mission_for(participant.character_sheet),
    )


def award_unrolled(
    participant: CombatParticipant,
    action: CombatRoundAction | None,
    *,
    kind: str,
    target: CharacterSheet | None = None,
    aids: bool = False,
) -> None:
    """Earn what a PC's act feeds when the act rolled nothing of its own (covering an ally).

    It earns at the plainest success: the ``KindledDeedAward`` of the lowest-success-level
    ``CheckOutcome`` (``lowest_success_outcome``).
    """
    award_rolled(
        participant,
        action,
        kind=kind,
        outcome=lowest_success_outcome(),
        target=target,
        aids=aids,
    )


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
    award_rolled(
        participant,
        action,
        kind=KindlingActKind.TECHNIQUE,
        outcome=check.outcome,
        aids=action.focused_ally_target is not None,
    )


def award_defense_deed(
    participant: CombatParticipant, attacker: CombatOpponent, outcome: CheckOutcome | None
) -> None:
    """Earn what defending against ``attacker`` feeds (#5124), scaled by the defense roll.

    The attacker is the act's target when it is a persona-backed opponent.
    """
    persona = attacker.persona
    award_rolled(
        participant,
        None,
        kind=KindlingActKind.DEFEND,
        outcome=outcome,
        target=persona.character_sheet if persona is not None else None,
    )


def award_for_strike(
    participant: CombatParticipant, action: CombatRoundAction, hit: CheckResult
) -> None:
    """Earn the resonances a Strike feeds, scaled by its hit roll."""
    award_rolled(participant, action, kind=KindlingActKind.ATTACK, outcome=hit.outcome)
