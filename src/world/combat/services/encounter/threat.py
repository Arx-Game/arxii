"""Threat records and threat accumulation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.models import CombatEncounter, CombatOpponent, CombatParticipant, ThreatRecord

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


# ---------------------------------------------------------------------------
# Threat record helpers (#2020)
# ---------------------------------------------------------------------------


def get_or_create_threat_record(
    encounter: CombatEncounter,
    opponent: CombatOpponent,
    participant: CombatParticipant,
) -> ThreatRecord:
    """Get or create the ThreatRecord for an (opponent, participant) pairing (#2020).

    Args:
        encounter: The combat encounter.
        opponent: The NPC opponent.
        participant: The PC participant.

    Returns:
        The existing or newly-created ``ThreatRecord`` for this pairing.
    """
    record, _ = ThreatRecord.objects.get_or_create(
        encounter=encounter,
        opponent=opponent,
        participant=participant,
        defaults={"threat_value": 0},
    )
    return record


def accumulate_threat(
    encounter: CombatEncounter,
    opponent: CombatOpponent,
    participant: CombatParticipant,
    amount: int,
) -> None:
    """Increment the threat value for an (opponent, participant) pairing (#2020).

    Called from ``apply_damage_to_opponent`` (damage -> threat) and the taunt
    verb (#2015). ``amount`` is a positive integer; negative values are clamped
    to zero.

    Args:
        encounter: The combat encounter.
        opponent: The NPC opponent being threatened against.
        participant: The PC participant whose threat is accumulating.
        amount: The threat increment (clamped to >= 0).
    """
    record = get_or_create_threat_record(encounter, opponent, participant)
    record.threat_value = max(0, record.threat_value + amount)
    record.save(update_fields=["threat_value"])


def _accumulate_damage_threat(
    opponent: CombatOpponent, source_sheet: CharacterSheet, damage_through: int
) -> None:
    """Credit post-soak damage to the dealer's ThreatRecord for this opponent (#2020)."""
    participant = CombatParticipant.objects.filter(
        encounter=opponent.encounter,
        character_sheet=source_sheet,
    ).first()
    if participant is not None:
        accumulate_threat(opponent.encounter, opponent, participant, damage_through)
