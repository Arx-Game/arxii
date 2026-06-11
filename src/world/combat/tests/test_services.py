"""Tests for combat encounter lifecycle service functions."""

from django.test import TestCase
import pytest

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import (
    ActionCategory,
    CombatManeuver,
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
from world.combat.models import CombatOpponentAction, CombatParticipant, FleeConfig
from world.combat.services import (
    add_opponent,
    add_participant,
    begin_declaration_phase,
    declare_action,
    declare_cover,
    declare_flee,
    get_flee_config,
    join_encounter,
    select_npc_actions,
)
from world.covenants.factories import CovenantRoleFactory
from world.fatigue.constants import EffortLevel
from world.magic.factories import EffectTypeFactory, GiftFactory, TechniqueFactory
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
            focused_opponent_target=self.opponent,
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
        """Raises ValueError if the participant cannot act (Unconscious → awareness 0).

        Eligibility now gates on can_act (awareness capability), not the removed
        vitals.status field. Applying an Unconscious condition that zeroes the
        AWARENESS capability is the canonical incapacitation path.
        """
        from world.conditions.constants import FoundationalCapability
        from world.conditions.factories import (
            CapabilityTypeFactory,
            ConditionCapabilityEffectFactory,
            UnconsciousConditionFactory,
        )
        from world.conditions.services import apply_condition

        awareness = CapabilityTypeFactory(name=FoundationalCapability.AWARENESS, innate_baseline=1)
        condition = UnconsciousConditionFactory()
        ConditionCapabilityEffectFactory(condition=condition, capability=awareness, value=-100)
        apply_condition(target=self.participant.character_sheet.character, condition=condition)
        with self.assertRaisesRegex(ValueError, "dead or incapacitated"):
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


class JoinEncounterTest(TestCase):
    """Tests for join_encounter service function."""

    def test_player_joins_active_encounter(self) -> None:
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        CombatOpponentFactory(encounter=encounter)
        sheet = CharacterSheetFactory()
        participant = join_encounter(encounter, sheet)
        assert participant.encounter == encounter
        assert participant.status == ParticipantStatus.ACTIVE

    def test_cannot_join_completed_encounter(self) -> None:
        encounter = CombatEncounterFactory(status=EncounterStatus.COMPLETED)
        sheet = CharacterSheetFactory()
        with pytest.raises(ValueError, match="Can only join during declaration or between rounds"):
            join_encounter(encounter, sheet)

    def test_cannot_join_twice(self) -> None:
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        CombatOpponentFactory(encounter=encounter)
        sheet = CharacterSheetFactory()
        join_encounter(encounter, sheet)
        with pytest.raises(ValueError, match="Already participating"):
            join_encounter(encounter, sheet)

    def test_can_join_between_rounds(self) -> None:
        encounter = CombatEncounterFactory(
            status=EncounterStatus.BETWEEN_ROUNDS,
        )
        CombatOpponentFactory(encounter=encounter)
        sheet = CharacterSheetFactory()
        participant = join_encounter(encounter, sheet)
        assert participant.status == ParticipantStatus.ACTIVE


class DeclareFleeTest(TestCase):
    """Tests for declare_flee service function."""

    def _make_participant(
        self, status: str = EncounterStatus.DECLARING, health: int = 50
    ) -> CombatParticipant:
        encounter = CombatEncounterFactory(status=status, round_number=1)
        participant = CombatParticipantFactory(encounter=encounter)
        CharacterVitals.objects.create(
            character_sheet=participant.character_sheet,
            health=health,
            max_health=100,
        )
        return participant

    def test_declares_flee_action(self) -> None:
        participant = self._make_participant()
        action = declare_flee(participant)
        assert action.focused_action is None
        assert action.focused_category is None
        assert action.is_ready is True

    def test_declare_flee_sets_maneuver_not_fled_status(self) -> None:
        """declare_flee sets maneuver=FLEE and leaves participant ACTIVE (no immediate FLED)."""
        participant = self._make_participant()
        action = declare_flee(participant)
        assert action.maneuver == CombatManeuver.FLEE
        participant.refresh_from_db()
        assert participant.status == ParticipantStatus.ACTIVE

    def test_cannot_flee_outside_declaring(self) -> None:
        participant = self._make_participant(status=EncounterStatus.BETWEEN_ROUNDS)
        with pytest.raises(ValueError, match="expected 'Declaring'"):
            declare_flee(participant)

    def test_cannot_flee_when_dead(self) -> None:
        """Dead characters (life_state=DEAD) cannot declare flee."""
        from world.vitals.constants import CharacterLifeState

        encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
        participant = CombatParticipantFactory(encounter=encounter)
        CharacterVitals.objects.create(
            character_sheet=participant.character_sheet,
            health=0,
            max_health=100,
            life_state=CharacterLifeState.DEAD,
        )
        with pytest.raises(ValueError, match="dead"):
            declare_flee(participant)

    def test_redeclare_action_after_flee_clears_maneuver(self) -> None:
        """Calling declare_action after declare_flee resets maneuver to None."""
        effect_type = EffectTypeFactory(name="FleeReDeclare", base_power=20)
        gift = GiftFactory()
        participant = self._make_participant()
        opponent = CombatOpponentFactory(encounter=participant.encounter)
        technique = TechniqueFactory(gift=gift, effect_type=effect_type)

        declare_flee(participant)
        action = declare_action(
            participant,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=opponent,
        )
        assert action.maneuver is None

    def test_redeclare_flee_after_cover_clears_ally_target(self) -> None:
        """Re-declaring flee after cover sets maneuver=FLEE and focused_ally_target=None."""
        encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
        participant = CombatParticipantFactory(encounter=encounter)
        ally = CombatParticipantFactory(encounter=encounter)
        CharacterVitals.objects.create(
            character_sheet=participant.character_sheet, health=50, max_health=100
        )
        CharacterVitals.objects.create(
            character_sheet=ally.character_sheet, health=50, max_health=100
        )

        declare_cover(participant, ally)
        action = declare_flee(participant)
        assert action.focused_ally_target is None
        assert action.maneuver == CombatManeuver.FLEE


class DeclareCoverTest(TestCase):
    """Tests for declare_cover service function."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.ally = CombatParticipantFactory(encounter=self.encounter)
        CharacterVitals.objects.create(
            character_sheet=self.participant.character_sheet, health=50, max_health=100
        )
        CharacterVitals.objects.create(
            character_sheet=self.ally.character_sheet, health=50, max_health=100
        )

    def test_declare_cover_sets_maneuver_and_ally(self) -> None:
        """declare_cover creates an action with maneuver=COVER, the ally target, is_ready=True."""
        action = declare_cover(self.participant, self.ally)
        assert action.maneuver == CombatManeuver.COVER
        assert action.focused_ally_target == self.ally
        assert action.is_ready is True
        self.participant.refresh_from_db()
        assert self.participant.status == ParticipantStatus.ACTIVE

    def test_declare_cover_rejects_self(self) -> None:
        """Cannot cover yourself."""
        with pytest.raises(ValueError, match="Cannot cover yourself"):
            declare_cover(self.participant, self.participant)

    def test_declare_cover_rejects_inactive_or_foreign_ally(self) -> None:
        """Ally must be active and in the same encounter."""
        # Inactive ally (FLED) in the same encounter
        self.ally.status = ParticipantStatus.FLED
        self.ally.save(update_fields=["status"])
        with pytest.raises(ValueError, match="active participant in this encounter"):
            declare_cover(self.participant, self.ally)

        # Foreign encounter ally
        other_encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
        foreign_ally = CombatParticipantFactory(encounter=other_encounter)
        CharacterVitals.objects.create(
            character_sheet=foreign_ally.character_sheet, health=50, max_health=100
        )
        with pytest.raises(ValueError, match="active participant in this encounter"):
            declare_cover(self.participant, foreign_ally)

    def test_declare_cover_rejects_outside_declaring(self) -> None:
        """Cannot cover outside DECLARING status."""
        self.encounter.status = EncounterStatus.BETWEEN_ROUNDS
        self.encounter.save(update_fields=["status"])
        with pytest.raises(ValueError, match="expected 'Declaring'"):
            declare_cover(self.participant, self.ally)


class GetFleeConfigTest(TestCase):
    """Tests for get_flee_config service function."""

    def test_raises_does_not_exist_when_unseeded(self) -> None:
        """get_flee_config raises FleeConfig.DoesNotExist when no row exists."""
        FleeConfig.objects.filter(pk=1).delete()
        with pytest.raises(FleeConfig.DoesNotExist):
            get_flee_config()

    def test_returns_row_when_present(self) -> None:
        """get_flee_config returns the singleton when seeded."""
        check_type = CheckTypeFactory(name="flee-test")
        FleeConfig.objects.filter(pk=1).delete()
        config = FleeConfig.objects.create(pk=1, check_type=check_type)
        result = get_flee_config()
        assert result.pk == config.pk
        assert result.check_type == check_type
