"""Tests for the lethal-duel risk-acknowledgement guard in declare_action (Task 12b).

A PC placed into a lethal DUEL by ``create_lethal_duel`` is deliberately NOT
auto-acknowledged. The #777 outsider gate does not apply to an already-active
participant, so without this guard such a PC could act without ever acknowledging
the lethal risk. ``declare_action`` therefore blocks a participant in a lethal DUEL
from declaring until an ``EncounterRiskAcknowledgement`` row exists.

Scope: the guard fires only for ``encounter_type == DUEL`` AND ``is_lethal`` AND no
ack row. Lethal party-combat PCs self-join via ``join_encounter`` (which records an
ack), so they are out of scope; GM-placed party-combat PCs (``add_participant``, no
ack) must not be blocked either, hence the DUEL-only scoping.
"""

from django.test import TestCase

from world.combat.constants import EncounterType, RiskLevel
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import EncounterRiskAcknowledgement
from world.combat.services import acknowledge_encounter_risk, declare_action
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


def _participant_in(encounter) -> object:
    """Create an ACTIVE participant with ALIVE vitals in *encounter*, plus an opponent."""
    participant = CombatParticipantFactory(encounter=encounter)
    CharacterVitals.objects.create(
        character_sheet=participant.character_sheet, health=100, max_health=100
    )
    CombatOpponentFactory(encounter=encounter)
    return participant


class LethalDuelAckGuardTests(TestCase):
    """declare_action blocks a lethal-DUEL PC until they acknowledge the risk."""

    def test_lethal_duel_without_ack_blocks_declaration(self) -> None:
        encounter = CombatEncounterFactory(
            encounter_type=EncounterType.DUEL,
            risk_level=RiskLevel.LETHAL,
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        participant = _participant_in(encounter)

        with self.assertRaises(ValueError) as ctx:
            declare_action(participant, effort_level=EffortLevel.MEDIUM)
        self.assertIn("acknowledge", str(ctx.exception).lower())

    def test_lethal_duel_with_ack_allows_declaration(self) -> None:
        encounter = CombatEncounterFactory(
            encounter_type=EncounterType.DUEL,
            risk_level=RiskLevel.LETHAL,
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        participant = _participant_in(encounter)
        acknowledge_encounter_risk(encounter, participant.character_sheet)

        action = declare_action(participant, effort_level=EffortLevel.MEDIUM)
        self.assertIsNotNone(action)

    def test_non_lethal_duel_not_blocked(self) -> None:
        encounter = CombatEncounterFactory(
            encounter_type=EncounterType.DUEL,
            risk_level=RiskLevel.MODERATE,
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        participant = _participant_in(encounter)
        # No ack row — but non-lethal, so the guard must not fire.
        self.assertFalse(
            EncounterRiskAcknowledgement.objects.filter(
                encounter=encounter, character_sheet=participant.character_sheet
            ).exists()
        )

        action = declare_action(participant, effort_level=EffortLevel.MEDIUM)
        self.assertIsNotNone(action)

    def test_lethal_party_combat_not_blocked(self) -> None:
        """A lethal PARTY_COMBAT PC without an ack row is out of scope (DUEL-only guard)."""
        encounter = CombatEncounterFactory(
            encounter_type=EncounterType.PARTY_COMBAT,
            risk_level=RiskLevel.LETHAL,
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        participant = _participant_in(encounter)
        self.assertFalse(
            EncounterRiskAcknowledgement.objects.filter(
                encounter=encounter, character_sheet=participant.character_sheet
            ).exists()
        )

        action = declare_action(participant, effort_level=EffortLevel.MEDIUM)
        self.assertIsNotNone(action)
