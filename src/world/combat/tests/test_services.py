"""Tests for combat encounter lifecycle service functions."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    ActionCategory,
    EncounterStatus,
    OpponentStatus,
    OpponentTier,
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
from world.combat.models import CombatOpponentAction
from world.combat.services import (
    add_opponent,
    add_participant,
    begin_declaration_phase,
    declare_action,
    select_npc_actions,
)
from world.covenants.factories import CovenantRoleFactory
from world.fatigue.constants import EffortLevel
from world.magic.factories import EffectTypeFactory, GiftFactory, TechniqueFactory
from world.vitals.constants import CharacterStatus
from world.vitals.models import CharacterVitals


class AddParticipantTest(TestCase):
    """Tests for add_participant service function."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.role = CovenantRoleFactory(speed_rank=3)

    def test_adds_participant(self) -> None:
        encounter = CombatEncounterFactory()
        sheet = CharacterSheetFactory()
        p = add_participant(encounter, sheet)
        assert p.encounter == encounter
        assert p.character_sheet == sheet
        assert p.covenant_role is None

    def test_adds_participant_with_covenant_role(self) -> None:
        encounter = CombatEncounterFactory()
        sheet = CharacterSheetFactory()
        p = add_participant(encounter, sheet, covenant_role=self.role)
        assert p.covenant_role == self.role


class AddOpponentTest(TestCase):
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


class BeginDeclarationPhaseTest(TestCase):
    """Tests for begin_declaration_phase service function."""

    def test_advances_round_and_sets_status(self) -> None:
        encounter = CombatEncounterFactory()
        CombatOpponentFactory(encounter=encounter)
        self.assertEqual(encounter.round_number, 0)

        begin_declaration_phase(encounter)
        self.assertEqual(encounter.round_number, 1)
        self.assertEqual(encounter.status, EncounterStatus.DECLARING)

    def test_subsequent_call_advances_to_round_2(self) -> None:
        encounter = CombatEncounterFactory()
        CombatOpponentFactory(encounter=encounter)

        begin_declaration_phase(encounter)
        self.assertEqual(encounter.round_number, 1)

        # Reset status to BETWEEN_ROUNDS before calling again
        encounter.status = EncounterStatus.BETWEEN_ROUNDS
        encounter.save(update_fields=["status"])

        begin_declaration_phase(encounter)
        self.assertEqual(encounter.round_number, 2)
        self.assertEqual(encounter.status, EncounterStatus.DECLARING)

    def test_rejects_non_between_rounds_status(self) -> None:
        encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING)
        CombatOpponentFactory(encounter=encounter)
        with self.assertRaises(ValueError, msg="expected 'Between Rounds'"):
            begin_declaration_phase(encounter)

    def test_rejects_completed_status(self) -> None:
        encounter = CombatEncounterFactory(status=EncounterStatus.COMPLETED)
        CombatOpponentFactory(encounter=encounter)
        with self.assertRaises(ValueError):
            begin_declaration_phase(encounter)

    def test_rejects_no_opponents(self) -> None:
        encounter = CombatEncounterFactory(status=EncounterStatus.BETWEEN_ROUNDS)
        with self.assertRaises(ValueError, msg="no active opponents"):
            begin_declaration_phase(encounter)


class SelectNpcActionsTest(TestCase):
    """Tests for select_npc_actions service function."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory(round_number=1, status=EncounterStatus.DECLARING)
        self.pool = ThreatPoolFactory()
        self.entry = ThreatPoolEntryFactory(
            pool=self.pool,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.RANDOM,
        )
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
        )
        CharacterVitals.objects.create(
            character_sheet=self.participant.character_sheet,
            health=100,
            max_health=100,
            status=CharacterStatus.ALIVE,
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

    def test_rejects_non_declaring_status(self) -> None:
        self.encounter.status = EncounterStatus.BETWEEN_ROUNDS
        self.encounter.save(update_fields=["status"])
        with self.assertRaises(ValueError, msg="expected 'Declaring'"):
            select_npc_actions(self.encounter)

    def test_rejects_resolving_status(self) -> None:
        self.encounter.status = EncounterStatus.RESOLVING
        self.encounter.save(update_fields=["status"])
        with self.assertRaises(ValueError):
            select_npc_actions(self.encounter)

    def test_cooldown_excludes_recently_used_entry(self) -> None:
        """An entry on cooldown should not be selected."""
        # Use round 3 so cooldown math is clear: cooldown=2 means
        # earliest_allowed = max(1, 3-2+1) = 2, and we used it at round 2.
        encounter = CombatEncounterFactory(round_number=3, status=EncounterStatus.DECLARING)
        pool = ThreatPoolFactory()
        normal_entry = ThreatPoolEntryFactory(pool=pool, weight=1)
        cooldown_entry = ThreatPoolEntryFactory(
            pool=pool,
            cooldown_rounds=2,
            weight=1000,  # Would always be picked if eligible
        )
        cooldown_participant = CombatParticipantFactory(encounter=encounter)
        CharacterVitals.objects.create(
            character_sheet=cooldown_participant.character_sheet,
            health=100,
            max_health=100,
            status=CharacterStatus.ALIVE,
        )
        opponent = CombatOpponentFactory(encounter=encounter, threat_pool=pool)
        CombatOpponentAction.objects.create(
            opponent=opponent,
            round_number=2,
            threat_entry=cooldown_entry,
        )
        actions = select_npc_actions(encounter)
        self.assertEqual(len(actions), 1)
        # Should have picked normal_entry, not cooldown_entry
        self.assertEqual(actions[0].threat_entry, normal_entry)


class DeclareActionTest(TestCase):
    """Tests for declare_action service function."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect_type = EffectTypeFactory(name="Attack", base_power=20)
        cls.gift = GiftFactory()

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        CharacterVitals.objects.create(
            character_sheet=self.participant.character_sheet,
            health=100,
            max_health=100,
            status=CharacterStatus.ALIVE,
        )
        self.technique = TechniqueFactory(gift=self.gift, effect_type=self.effect_type)
        self.opponent = CombatOpponentFactory(encounter=self.encounter)

    def test_declare_action_valid(self) -> None:
        """A valid action declaration creates a CombatRoundAction."""
        action = declare_action(
            self.participant,
            focused_action=self.technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_target=self.opponent,
        )
        self.assertEqual(action.participant, self.participant)
        self.assertEqual(action.round_number, 1)
        self.assertEqual(action.focused_action, self.technique)
        self.assertEqual(action.focused_category, ActionCategory.PHYSICAL)

    def test_declare_action_wrong_status(self) -> None:
        """Raises ValueError if encounter is not DECLARING."""
        self.encounter.status = EncounterStatus.BETWEEN_ROUNDS
        self.encounter.save(update_fields=["status"])
        with self.assertRaises(ValueError, msg="expected 'Declaring'"):
            declare_action(
                self.participant,
                focused_action=self.technique,
                focused_category=ActionCategory.PHYSICAL,
                effort_level=EffortLevel.MEDIUM,
            )

    def test_declare_action_unconscious_participant(self) -> None:
        """Raises ValueError if participant is UNCONSCIOUS."""
        vitals = CharacterVitals.objects.get(character_sheet=self.participant.character_sheet)
        vitals.status = CharacterStatus.UNCONSCIOUS
        vitals.save(update_fields=["status"])
        with self.assertRaises(ValueError, msg="character status"):
            declare_action(
                self.participant,
                focused_action=self.technique,
                focused_category=ActionCategory.PHYSICAL,
                effort_level=EffortLevel.MEDIUM,
            )

    def test_declare_action_passive_matches_focus_rejected(self) -> None:
        """Raises ValueError if physical passive provided when focused on physical."""
        other_technique = TechniqueFactory(gift=self.gift, effect_type=self.effect_type)
        with self.assertRaises(ValueError, msg="passive must be None"):
            declare_action(
                self.participant,
                focused_action=self.technique,
                focused_category=ActionCategory.PHYSICAL,
                effort_level=EffortLevel.MEDIUM,
                physical_passive=other_technique,
            )
