"""Risk acknowledgement and the solo-boss entry warning."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import OpponentStatus, OpponentTier, ParticipantStatus
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    EncounterRiskAcknowledgement,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def acknowledge_encounter_risk(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
) -> EncounterRiskAcknowledgement:
    """Idempotently record that a character acknowledged the encounter's risk (#777).

    Called at every voluntary entry: self-join, hostile-cast initiation, and
    consent-accept. The level is snapshotted at first acknowledgement.
    """
    ack, created = EncounterRiskAcknowledgement.objects.get_or_create(
        encounter=encounter,
        character_sheet=character_sheet,
        defaults={"acknowledged_risk_level": encounter.risk_level},
    )
    # #2051: on first entry, warn a solo character entering a BOSS/HERO_KILLER
    # encounter — the stark darkness line, no gate (decision 2).
    if created:
        _maybe_warn_solo_boss_entry(encounter, character_sheet)
    return ack


def _maybe_warn_solo_boss_entry(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
) -> None:
    """Send the solo darkness warning if entering a BOSS/HERO_KILLER encounter alone (#2051)."""
    from world.missions.constants import SOLO_DARKNESS_WARNING  # noqa: PLC0415

    has_boss = CombatOpponent.objects.filter(
        encounter=encounter,
        tier__in=(OpponentTier.BOSS, OpponentTier.HERO_KILLER),
        status=OpponentStatus.ACTIVE,
    ).exists()
    if not has_boss:
        return
    # Check if the character is the only active participant (solo).
    active_count = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).count()
    if active_count > 1:
        return
    character_sheet.character.msg(SOLO_DARKNESS_WARNING)
