"""Battle-conclusion win-gated LegendEntry wiring (#2184).

Registered as a ``world.battles.conclusion_hooks`` hook in
``world.battles.apps.ready()`` — mirrors ``world.ships.battle_wiring``'s shape,
but here ``battles`` importing ``societies`` is the ratified direction (both
are general/reusable systems; societies' legend model has no reason to know
about battles, so the dependency runs the other way).

Only the winning side's participants + winning-side unit commanders earn a
shared Victory deed. Separately, any resolved battle-round declaration with a
standout success on a dramatic action kind (RESCUE/ROUT/BREACH) earns its actor
a smaller solo deed, regardless of which side they were on — a losing-side
rescue is still a story worth telling.

**#3467: this module now decides WHO, not HOW MUCH.** Pricing moved to
``world.battles.legend_settlement``, which routes through the shared settlement
seam: the peril floor applied per person, the held-objective share, and a
station stamp. The flat BATTLE_LEGEND_* constants are gone — a battle's Legend
comes from its beat's risk tier via ``RiskCalibration.legend_award``, like every
other source. A battle with no staked beat has no target level, so no station,
so no advancement Legend.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.battles.constants import (
    DRAMATIC_KINDS,
    STANDOUT_SUCCESS_LEVEL,
    BattleActionKind,
    BattleOutcome,
    BattleSideRole,
)
from world.battles.legend_settlement import settle_legend_for_battle
from world.battles.models import BattleActionDeclaration, BattleParticipant, BattleUnit
from world.societies.models import LegendEntry, LegendSourceType

if TYPE_CHECKING:
    from world.battles.models import Battle
    from world.character_sheets.models import CharacterSheet

logger = logging.getLogger(__name__)

# Which side won, and whether it was decisive, per graded BattleOutcome.
# UNRESOLVED has no entry — callers must check membership before indexing.
_WINNING_SIDE_BY_OUTCOME: dict[str, tuple[str, bool]] = {
    BattleOutcome.ATTACKER_DECISIVE: (BattleSideRole.ATTACKER, True),
    BattleOutcome.ATTACKER_MARGINAL: (BattleSideRole.ATTACKER, False),
    BattleOutcome.DEFENDER_DECISIVE: (BattleSideRole.DEFENDER, True),
    BattleOutcome.DEFENDER_MARGINAL: (BattleSideRole.DEFENDER, False),
}

# Standout-deed title per dramatic action kind, formatted with the battle name.
STANDOUT_TITLES: dict[str, str] = {
    BattleActionKind.RESCUE: "Daring rescue at {battle}",
    BattleActionKind.ROUT: "Decisive rout at {battle}",
    BattleActionKind.BREACH: "Breakthrough breach at {battle}",
}


def _battle_source_type() -> LegendSourceType:
    """Lazy ``LegendSourceType`` row for battle-earned legend (#2184).

    Mirrors the ``_theft_source_type``/``theft_category`` lazy-row idiom
    (``flows/service_functions/inventory.py``) — ``LegendSourceType`` has no
    fixed enum of members, so there's no committed "existing member" to grep;
    rows are get-or-created on first use instead of fixture-seeded (fixtures
    aren't in version control, ADR-0013 bans seed migrations).
    """
    source_type, _ = LegendSourceType.objects.get_or_create(
        name="Battle",
        defaults={"description": "War-scale battle victories and standout deeds."},
    )
    return source_type


def _winning_sheets(battle: Battle, winning_side_role: str) -> list[CharacterSheet]:
    """Every winning-side participant + winning-side unit commander, deduped by sheet.

    Returns SHEETS rather than personas since #3467: settlement needs each
    earner's level to compute their station and personal risk, and resolves the
    persona itself.
    """
    sheets: dict[int, CharacterSheet] = {}

    participants = BattleParticipant.objects.filter(
        battle=battle, side__role=winning_side_role
    ).select_related("character_sheet")
    for participant in participants:
        sheets[participant.character_sheet_id] = participant.character_sheet

    commanded_units = BattleUnit.objects.filter(
        battle=battle, side__role=winning_side_role, military_unit__commander__isnull=False
    ).select_related("military_unit__commander")
    for unit in commanded_units:
        sheets[unit.military_unit.commander_id] = unit.military_unit.commander

    return list(sheets.values())


def _standout_sheets(battle: Battle) -> list[CharacterSheet]:
    """Sheets with a standout DRAMATIC action, either side (ADR-0122).

    The recipient set for the standout pass. Pricing and minting moved to
    ``world.battles.legend_settlement`` in #3467; this stays because *who
    counts* is a battle question, and ADR-0122's answer — RESCUE/ROUT/BREACH at
    or above the standout bar, winners and losers alike — is deliberately
    narrower than "any high roll".
    """
    declarations = BattleActionDeclaration.objects.filter(
        participant__battle=battle,
        resolved=True,
        success_level__gte=STANDOUT_SUCCESS_LEVEL,
        action_kind__in=DRAMATIC_KINDS,
    ).select_related("participant__character_sheet")
    sheets: dict[int, CharacterSheet] = {}
    for declaration in declarations:
        sheet = declaration.participant.character_sheet
        sheets[sheet.pk] = sheet
    return list(sheets.values())


def apply_battle_legend_awards(battle: Battle) -> None:
    """Mint the winning side's Victory legend event + any standout solo deeds.

    Idempotent: no-ops if any ``LegendEntry`` with the Battle source type
    already exists for ``battle.scene`` (covers a hook re-run, e.g. a second
    ``conclude_battle`` call — which is itself idempotent, but the hook
    registry has no idempotency of its own).

    Args:
        battle: A just-concluded ``Battle`` (``battle.outcome`` set).
    """
    source_type = _battle_source_type()
    if LegendEntry.objects.filter(source_type=source_type, scene=battle.scene).exists():
        return

    mapping = _WINNING_SIDE_BY_OUTCOME.get(battle.outcome)
    if mapping is None:
        # UNRESOLVED (or any future non-graded outcome) — nothing to mint.
        return
    winning_side_role, _decisive = mapping

    # #3467: the decisive/marginal split no longer picks a flat value. What a
    # battle pays comes from its beat's risk through the shared settlement
    # seam, and how much each person earns comes from their own station and
    # personal risk. The outcome mapping survives only to name the winning side.
    report = settle_legend_for_battle(
        battle,
        winning_sheets=_winning_sheets(battle, winning_side_role),
        standout_sheets=_standout_sheets(battle),
        source_type=source_type,
    )
    if not report.minted:
        logger.info("Battle %s minted no Legend: %s", battle.pk, report.reason)
