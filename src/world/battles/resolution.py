"""Battle round resolution engine.

Iterates all unresolved BattleActionDeclarations for a round, rolls
``perform_check`` once per declaration, then routes the result:

- ``success_level > 0`` → STRIKE: attrite the target unit + award VP to the
  participant's side; SUPPORT: award SUPPORT_VP.
- ``success_level <= 0`` → debit PC health then call
  ``process_damage_consequences`` (non-progressive, SQLite-safe).

The ``BattleRoundResult`` dataclass carries per-side VP totals, routed/
destroyed unit lists, and a casualty list for the caller to display or log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.utils import timezone

from world.battles.constants import (
    BASE_FAILURE_DAMAGE,
    BATTLE_CHECK_TYPE_NAME,
    STRIKE_ATTRITION_PER_LEVEL,
    STRIKE_VP_PER_LEVEL,
    SUPPORT_VP,
    BattleActionKind,
    BattleUnitStatus,
)
from world.battles.models import BattleRound
from world.checks.services import perform_check
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.battles.models import BattleActionDeclaration
    from world.checks.models import CheckType


@dataclass
class BattleRoundResult:
    """Summary of a resolved battle round."""

    # VP awarded per BattleSide pk → total awarded this round.
    vp_awarded: dict[int, int] = field(default_factory=dict)
    # Units whose strength reached 0 and were DESTROYED this round.
    units_destroyed: list[int] = field(default_factory=list)
    # Units whose strength fell below the ROUTED threshold (but not 0).
    units_routed: list[int] = field(default_factory=list)
    # Participant pks who took damage this round.
    casualties: list[int] = field(default_factory=list)


def get_battle_check_type() -> CheckType:
    """Return the ``CheckType`` used for all battle action checks.

    Raises:
        CheckType.DoesNotExist: If the "Battle Action" check type is not seeded.
    """
    from world.checks.models import CheckType  # noqa: PLC0415

    return CheckType.objects.get(name=BATTLE_CHECK_TYPE_NAME)


def _resolve_strike_success(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,
    success_level: int,
) -> None:
    """Apply STRIKE success: attrite the unit, award VP to the participant's side."""
    unit = declaration.target_unit
    if unit is None:
        return

    attrition = success_level * STRIKE_ATTRITION_PER_LEVEL
    unit.strength = max(0, unit.strength - attrition)

    if unit.strength == 0:
        unit.status = BattleUnitStatus.DESTROYED
        result.units_destroyed.append(unit.pk)
    elif unit.strength <= 30:  # noqa: PLR2004 — strength ≤ 30 = routed threshold
        unit.status = BattleUnitStatus.ROUTED
        result.units_routed.append(unit.pk)

    unit.save(update_fields=["strength", "status"])

    side = declaration.participant.side
    vp_gain = success_level * STRIKE_VP_PER_LEVEL
    side.victory_points += vp_gain
    side.save(update_fields=["victory_points"])

    result.vp_awarded[side.pk] = result.vp_awarded.get(side.pk, 0) + vp_gain


def _resolve_support_success(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,
) -> None:
    """Apply SUPPORT success: award SUPPORT_VP to the participant's side."""
    side = declaration.participant.side
    side.victory_points += SUPPORT_VP
    side.save(update_fields=["victory_points"])
    result.vp_awarded[side.pk] = result.vp_awarded.get(side.pk, 0) + SUPPORT_VP


def _resolve_failure(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,
    success_level: int,
) -> None:
    """Apply check failure: debit PC health then route through damage consequences.

    Damage is non-progressive (damage_type=None, source_character=None) so
    the SQLite fast tier can handle it without DISTINCT ON queries.
    """
    from world.vitals.services import process_damage_consequences  # noqa: PLC0415

    sheet = declaration.participant.character_sheet
    try:
        vitals = sheet.vitals
    except Exception:  # noqa: BLE001 — graceful if vitals not seeded
        result.casualties.append(declaration.participant.pk)
        return

    dmg = BASE_FAILURE_DAMAGE + abs(success_level)
    vitals.health -= dmg
    vitals.save(update_fields=["health"])

    process_damage_consequences(
        character_sheet=sheet,
        damage_dealt=dmg,
        damage_type=None,
        source_character=None,
    )
    result.casualties.append(declaration.participant.pk)


def resolve_battle_round(*, battle_round: BattleRound) -> BattleRoundResult:
    """Resolve all unresolved declarations for ``battle_round``.

    For each unresolved declaration, calls ``perform_check`` against the
    character's ObjectDB and routes success / failure to the appropriate
    sub-handlers.  Sets ``battle_round.status = COMPLETED`` at the end.

    Args:
        battle_round: The ``BattleRound`` in DECLARING or RESOLVING status.

    Returns:
        A ``BattleRoundResult`` summarising what happened this round.
    """
    check_type = get_battle_check_type()
    result = BattleRoundResult()

    declarations = list(
        battle_round.declarations.filter(resolved=False).select_related(
            "participant__character_sheet",
            "participant__side",
            "target_unit",
        )
    )

    for declaration in declarations:
        actor_objectdb = declaration.participant.character_sheet.character
        check_result = perform_check(actor_objectdb, check_type)
        sl = check_result.success_level

        if sl > 0:
            if declaration.action_kind == BattleActionKind.STRIKE:
                _resolve_strike_success(declaration, result, sl)
            else:
                _resolve_support_success(declaration, result)
        else:
            _resolve_failure(declaration, result, sl)

        declaration.resolved = True
        declaration.success_level = sl
        declaration.save(update_fields=["resolved", "success_level"])

    battle_round.status = RoundStatus.COMPLETED
    battle_round.completed_at = timezone.now()
    battle_round.save(update_fields=["status", "completed_at"])

    return result
