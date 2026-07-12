"""Battle-conclusion win-gated LegendEntry wiring (#2184).

Registered as a ``world.battles.conclusion_hooks`` hook in
``world.battles.apps.ready()`` — mirrors ``world.ships.battle_wiring``'s shape,
but here ``battles`` importing ``societies`` is the ratified direction (both
are general/reusable systems; societies' legend model has no reason to know
about battles, so the dependency runs the other way).

Only the winning side's participants + winning-side unit commanders earn a
shared Victory ``LegendEvent`` (win-gated — a decisive win is worth more than a
marginal one, and a loss earns nothing from the event itself). Separately, any
resolved battle-round declaration with a standout success on a dramatic action
kind (RESCUE/ROUT/BREACH) earns its actor a smaller solo deed, regardless of
which side they were on — a losing-side rescue is still a story worth telling.
Standout deeds stack with the victory event by design.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.battles.constants import (
    BATTLE_LEGEND_DECISIVE_VALUE,
    BATTLE_LEGEND_MARGINAL_VALUE,
    BATTLE_LEGEND_STANDOUT_VALUE,
    DRAMATIC_KINDS,
    STANDOUT_SUCCESS_LEVEL,
    BattleActionKind,
    BattleOutcome,
    BattleSideRole,
)
from world.battles.models import BattleActionDeclaration, BattleParticipant, BattleUnit
from world.scenes.services import active_persona_for_sheet
from world.societies.models import LegendEntry, LegendSourceType
from world.societies.services import create_legend_event, create_solo_deed

if TYPE_CHECKING:
    from world.battles.models import Battle
    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Persona

# Which side won, and whether it was decisive, per graded BattleOutcome.
# UNRESOLVED has no entry — callers must check membership before indexing.
_WINNING_SIDE_BY_OUTCOME: dict[str, tuple[str, bool]] = {
    BattleOutcome.ATTACKER_DECISIVE: (BattleSideRole.ATTACKER, True),
    BattleOutcome.ATTACKER_MARGINAL: (BattleSideRole.ATTACKER, False),
    BattleOutcome.DEFENDER_DECISIVE: (BattleSideRole.DEFENDER, True),
    BattleOutcome.DEFENDER_MARGINAL: (BattleSideRole.DEFENDER, False),
}

# Standout-deed title per dramatic action kind, formatted with the battle name.
_STANDOUT_TITLES: dict[str, str] = {
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


def _winning_personas(battle: Battle, winning_side_role: str) -> list[Persona]:
    """Every winning-side participant + winning-side unit commander, deduped by sheet."""
    sheets: dict[int, CharacterSheet] = {}

    participants = BattleParticipant.objects.filter(
        battle=battle, side__role=winning_side_role
    ).select_related("character_sheet")
    for participant in participants:
        sheets[participant.character_sheet_id] = participant.character_sheet

    commanded_units = BattleUnit.objects.filter(
        battle=battle, side__role=winning_side_role, commander__isnull=False
    ).select_related("commander")
    for unit in commanded_units:
        sheets[unit.commander_id] = unit.commander

    return [active_persona_for_sheet(sheet) for sheet in sheets.values()]


def _award_standout_deeds(battle: Battle, source_type: LegendSourceType) -> None:
    """Solo deeds for standout dramatic actions, winners and losers alike."""
    declarations = BattleActionDeclaration.objects.filter(
        participant__battle=battle,
        resolved=True,
        success_level__gte=STANDOUT_SUCCESS_LEVEL,
        action_kind__in=DRAMATIC_KINDS,
    ).select_related("participant__character_sheet")
    for declaration in declarations:
        sheet = declaration.participant.character_sheet
        persona = active_persona_for_sheet(sheet)
        title_template = _STANDOUT_TITLES[declaration.action_kind]
        create_solo_deed(
            persona,
            title_template.format(battle=battle.name),
            source_type,
            BATTLE_LEGEND_STANDOUT_VALUE,
            scene=battle.scene,
        )


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
    winning_side_role, decisive = mapping

    personas = _winning_personas(battle, winning_side_role)
    base_value = BATTLE_LEGEND_DECISIVE_VALUE if decisive else BATTLE_LEGEND_MARGINAL_VALUE
    create_legend_event(
        f"Victory at {battle.name}",
        source_type,
        base_value,
        personas,
        scene=battle.scene,
        story=battle.campaign_story,
    )

    _award_standout_deeds(battle, source_type)
