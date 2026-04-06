"""Tests for combat encounter lifecycle service functions."""

from evennia.utils.test_resources import BaseEvenniaTest

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    CovenantRole,
    EncounterStatus,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.services import (
    add_opponent,
    add_participant,
    begin_declaration_phase,
    select_npc_actions,
)


class AddParticipantTest(BaseEvenniaTest):
    """Tests for add_participant service function."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory()
        self.sheet = CharacterSheetFactory()

    def test_adds_participant_with_health(self) -> None:
        participant = add_participant(self.encounter, self.sheet, max_health=120)
        self.assertEqual(participant.health, 120)
        self.assertEqual(participant.max_health, 120)
        self.assertEqual(participant.status, ParticipantStatus.ACTIVE)

    def test_adds_participant_with_covenant_role(self) -> None:
        participant = add_participant(
            self.encounter,
            self.sheet,
            max_health=100,
            covenant_role=CovenantRole.VANGUARD,
        )
        self.assertEqual(participant.covenant_role, CovenantRole.VANGUARD)


class AddOpponentTest(BaseEvenniaTest):
    """Tests for add_opponent service function."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory()
        self.pool = ThreatPoolFactory()

    def test_adds_mook(self) -> None:
        opponent = add_opponent(
            self.encounter,
            name="Goblin",
            tier=OpponentTier.MOOK,
            max_health=50,
            threat_pool=self.pool,
        )
        self.assertEqual(opponent.tier, OpponentTier.MOOK)
        self.assertEqual(opponent.health, 50)
        self.assertEqual(opponent.max_health, 50)

    def test_adds_boss_with_soak(self) -> None:
        opponent = add_opponent(
            self.encounter,
            name="Dragon",
            tier=OpponentTier.BOSS,
            max_health=500,
            threat_pool=self.pool,
            soak_value=80,
            probing_threshold=50,
        )
        self.assertEqual(opponent.soak_value, 80)
        self.assertEqual(opponent.probing_threshold, 50)


class BeginDeclarationPhaseTest(BaseEvenniaTest):
    """Tests for begin_declaration_phase service function."""

    def test_advances_round_and_sets_status(self) -> None:
        encounter = CombatEncounterFactory()
        self.assertEqual(encounter.round_number, 0)

        begin_declaration_phase(encounter)
        self.assertEqual(encounter.round_number, 1)
        self.assertEqual(encounter.status, EncounterStatus.DECLARING)

    def test_subsequent_call_advances_to_round_2(self) -> None:
        encounter = CombatEncounterFactory()

        begin_declaration_phase(encounter)
        self.assertEqual(encounter.round_number, 1)

        # Reset status to BETWEEN_ROUNDS before calling again
        encounter.status = EncounterStatus.BETWEEN_ROUNDS
        encounter.save(update_fields=["status"])

        begin_declaration_phase(encounter)
        self.assertEqual(encounter.round_number, 2)
        self.assertEqual(encounter.status, EncounterStatus.DECLARING)


class SelectNpcActionsTest(BaseEvenniaTest):
    """Tests for select_npc_actions service function."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory(round_number=1)
        self.pool = ThreatPoolFactory()
        self.entry = ThreatPoolEntryFactory(
            pool=self.pool,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.RANDOM,
        )
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
        )

    def test_selects_action_for_each_opponent(self) -> None:
        opponent = CombatOpponentFactory(encounter=self.encounter, threat_pool=self.pool)
        actions = select_npc_actions(self.encounter)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].opponent, opponent)
        self.assertEqual(actions[0].threat_entry, self.entry)

    def test_skips_defeated_opponents(self) -> None:
        CombatOpponentFactory(
            encounter=self.encounter,
            threat_pool=self.pool,
            status=OpponentStatus.DEFEATED,
        )
        actions = select_npc_actions(self.encounter)
        self.assertEqual(len(actions), 0)

    def test_targets_assigned_to_action(self) -> None:
        CombatOpponentFactory(encounter=self.encounter, threat_pool=self.pool)
        actions = select_npc_actions(self.encounter)
        self.assertEqual(len(actions), 1)
        targets = list(actions[0].targets.all())
        self.assertIn(self.participant, targets)
