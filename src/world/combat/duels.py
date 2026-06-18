"""Duel setup and lifecycle services.

Keeps duel-specific logic out of the already-large services.py. A duel is a
PC-vs-PC encounter: both PCs are CombatParticipants (they declare actions) AND
each is mirrored by a passive ephemeral-free CombatOpponent surface the OTHER
attacks.

Mirror wiring:
    mirror_A.mirrors_participant = participant_A  (A's body surface; B attacks it)
    mirror_B.mirrors_participant = participant_B  (B's body surface; A attacks it)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.combat.cast_seed import _opponent_kwargs_from_sheet
from world.combat.constants import EncounterStatus, EncounterType, RiskLevel
from world.combat.models import CombatEncounter, CombatOpponent, CombatParticipant
from world.combat.services import acknowledge_encounter_risk, add_opponent, add_participant

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet


def _make_mirror(enc: CombatEncounter, participant: CombatParticipant) -> CombatOpponent:
    """Create a passive mirror opponent surface for a PC participant.

    The mirror is built from the participant's CharacterSheet stats via
    ``_opponent_kwargs_from_sheet``, then ``mirrors_participant`` is set on the
    returned instance (``add_opponent`` does not accept it as a kwarg).

    Position sync: the mirror's position is left as the opponent's default
    (derived from its ObjectDB location). Reach degrades gracefully to SAME
    when no explicit position is stored — Task 15 wires reach for duels.
    """
    sheet = participant.character_sheet
    kwargs = _opponent_kwargs_from_sheet(sheet)
    mirror = add_opponent(enc, **kwargs)
    mirror.mirrors_participant = participant
    mirror.save(update_fields=["mirrors_participant"])
    return mirror


@transaction.atomic
def create_pvp_duel(
    challenger_sheet: CharacterSheet,
    challenged_sheet: CharacterSheet,
    room: ObjectDB,
    *,
    risk_level: str = RiskLevel.MODERATE,
) -> CombatEncounter:
    """Set up a symmetric PC-vs-PC duel encounter.

    Creates a DUEL encounter in DECLARING status with two participants and two
    passive mirror opponents, records risk acknowledgements for both, and
    returns the encounter.

    Args:
        challenger_sheet: The sheet of the PC initiating the duel.
        challenged_sheet: The sheet of the PC accepting the duel.
        room: The ObjectDB room where the encounter takes place.
        risk_level: Risk level for this duel; must not be LETHAL (PvP is never
            lethal). Defaults to MODERATE.

    Returns:
        The newly created CombatEncounter in DECLARING status.

    Raises:
        ValueError: If ``risk_level`` is LETHAL.
    """
    if risk_level == RiskLevel.LETHAL:
        msg = "PC-vs-PC duels can never be lethal."
        raise ValueError(msg)

    enc = CombatEncounter.objects.create(
        encounter_type=EncounterType.DUEL,
        room=room,
        risk_level=risk_level,
        status=EncounterStatus.DECLARING,
    )

    participant_a = add_participant(enc, challenger_sheet)
    participant_b = add_participant(enc, challenged_sheet)

    _make_mirror(enc, participant_a)
    _make_mirror(enc, participant_b)

    acknowledge_encounter_risk(enc, challenger_sheet)
    acknowledge_encounter_risk(enc, challenged_sheet)

    return enc
