"""Battle round resolution engine.

Iterates all unresolved BattleActionDeclarations for a round, casts each
declaration's technique once via ``resolve_battle_technique``, then routes
the result:

- ``success_level > 0`` → STRIKE: attrite the target unit + award VP to the
  participant's side; SUPPORT: award SUPPORT_VP.
- ``success_level <= 0`` → debit PC health then call
  ``process_damage_consequences`` (non-progressive, SQLite-safe).

The ``BattleRoundResult`` dataclass carries per-side VP totals, routed/
destroyed unit lists, and a casualty list for the caller to display or log.

This module also provides ``BattleTechniqueResolver`` and
``resolve_battle_technique``, which cast a declaration's ``technique`` through
the real magic envelope (``use_technique``). Routing through ``use_technique``
(rather than a generic shared check) means the check is sourced from the
player's actual technique (``technique.action_template.check_type``),
anima/Soulfray/mishap apply normally, and Audere/Audere Majora escalation
fires automatically (it's wired inside ``use_technique`` itself, Step 8c — no
separate call site is needed here). ``resolve_battle_round`` calls
``resolve_battle_technique`` per declaration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.battles.constants import (
    BASE_FAILURE_DAMAGE,
    ROUTED_STRENGTH_THRESHOLD,
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
    from evennia.objects.models import ObjectDB

    from world.battles.models import BattleActionDeclaration
    from world.checks.types import CheckResult
    from world.magic.models import Technique
    from world.magic.types.power_ledger import PowerLedger


@dataclass
class BattleTechniqueResolution:
    """Adapts ``use_technique``'s resolve_fn contract — exposes ``.check_result``
    for ``_resolve_check_result`` (``world/magic/services/techniques.py``)."""

    check_result: CheckResult


@dataclass
class BattleTechniqueResolver:
    """``resolve_fn`` passed to ``use_technique``: rolls the declared technique's
    own check. Battle has no damage-profile/condition application of its own —
    that stays in ``resolve_battle_round``'s STRIKE/SUPPORT/failure routing.
    """

    character: ObjectDB
    technique: Technique

    def __call__(
        self,
        *,
        power: int,  # noqa: ARG002 — battle doesn't scale effects off cast power
        ledger: PowerLedger,  # noqa: ARG002 — battle doesn't use the power ledger
        extra_modifiers: int = 0,
    ) -> BattleTechniqueResolution:
        check_type = self.technique.action_template.check_type
        check_result = perform_check(self.character, check_type, extra_modifiers=extra_modifiers)
        return BattleTechniqueResolution(check_result=check_result)


def resolve_battle_technique(*, declaration: BattleActionDeclaration) -> CheckResult | None:
    """Cast ``declaration.technique`` through the real magic envelope.

    Routes through ``use_technique`` so anima cost, Soulfray accumulation, and —
    critically — the Audere/Audere Majora escalation hook (Step 8c, fires
    unconditionally inside ``use_technique`` for every caller) all apply exactly
    as they would for any other cast. ``confirm_soulfray_risk=True`` because a
    batch round resolve cannot pause mid-batch for one participant's consent
    prompt — same reasoning ``resolve_accepted_cast`` uses for its consent-accept
    path.

    Args:
        declaration: A ``BattleActionDeclaration`` with ``technique`` set.

    Returns:
        The resolved ``CheckResult``, or ``None`` if the cast was interrupted
        before resolution (e.g. a reactive PRE_CAST cancellation) — the caller
        treats ``None`` as success_level 0 (failure).
    """
    from world.magic.services import use_technique  # noqa: PLC0415

    character = declaration.participant.character_sheet.character
    technique = declaration.technique
    resolver = BattleTechniqueResolver(character=character, technique=technique)

    result = use_technique(
        character=character,
        technique=technique,
        resolve_fn=resolver,
        confirm_soulfray_risk=True,
    )
    if not result.confirmed or result.resolution_result is None:
        return None
    return result.resolution_result.check_result


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
    elif unit.strength <= ROUTED_STRENGTH_THRESHOLD:
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
    from world.vitals.models import CharacterVitals  # noqa: PLC0415
    from world.vitals.services import process_damage_consequences  # noqa: PLC0415

    sheet = declaration.participant.character_sheet
    try:
        vitals = sheet.vitals
    except CharacterVitals.DoesNotExist:
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


@transaction.atomic
def resolve_battle_round(*, battle_round: BattleRound) -> BattleRoundResult:
    """Resolve all unresolved declarations for ``battle_round``.

    For each unresolved declaration, casts its declared technique through
    ``resolve_battle_technique`` (the real magic envelope) and routes
    success / failure to the appropriate sub-handlers. Sets
    ``battle_round.status = COMPLETED`` at the end.

    Args:
        battle_round: The ``BattleRound`` in DECLARING or RESOLVING status.

    Returns:
        A ``BattleRoundResult`` summarising what happened this round.
    """
    result = BattleRoundResult()

    declarations = list(
        battle_round.declarations.filter(resolved=False).select_related(
            "participant__character_sheet",
            "participant__side",
            "target_unit",
            "technique__action_template",
        )
    )

    for declaration in declarations:
        check_result = resolve_battle_technique(declaration=declaration)
        sl = check_result.success_level if check_result is not None else 0

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
