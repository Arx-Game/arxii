"""Tests for combat encounter lifecycle service functions."""

from unittest.mock import patch

from django.test import TestCase
import pytest

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectType
from world.checks.factories import CheckTypeFactory, ConsequenceEffectFactory, ConsequenceFactory
from world.checks.outcome_models import ConsequenceOutcome
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult
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
from world.combat.models import (
    CombatOpponentAction,
    CombatParticipant,
    FleeConfig,
    FleeTierModifier,
)
from world.combat.services import (
    add_opponent,
    add_participant,
    begin_declaration_phase,
    declare_action,
    declare_cover,
    declare_flee,
    get_flee_config,
    join_encounter,
    resolve_round,
    select_npc_actions,
)
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.services import get_active_conditions
from world.covenants.factories import CovenantRoleFactory
from world.fatigue.constants import EffortLevel
from world.magic.factories import EffectTypeFactory, GiftFactory, TechniqueFactory
from world.traits.factories import CheckOutcomeFactory
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

    def test_cannot_flee_when_already_fled(self) -> None:
        """A participant who has already fled (status=FLED) cannot declare flee again."""
        participant = self._make_participant()
        participant.status = ParticipantStatus.FLED
        participant.save(update_fields=["status"])
        with pytest.raises(ValueError, match="no longer active"):
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

    def test_cannot_cover_when_already_fled(self) -> None:
        """A participant who has already fled (status=FLED) cannot declare cover."""
        self.participant.status = ParticipantStatus.FLED
        self.participant.save(update_fields=["status"])
        with pytest.raises(ValueError, match="no longer active"):
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


class ResolveFleeTest(TestCase):
    """Tests for _resolve_flee inside resolve_round (#878).

    Flee resolves as a graded check during round resolution: PARTIAL or
    better escapes (PARTIAL at a cost via the consequence pool);
    FAILURE/BOTCH stays ACTIVE. Difficulty = base + max active-opponent
    tier modifier; covering allies add cover_bonus each.
    """

    BASE_DIFFICULTY = 50
    COVER_BONUS = 10

    @classmethod
    def setUpTestData(cls) -> None:
        # Lower speed rank than NPC_SPEED_RANK (15) → the fleer resolves first.
        cls.fast_role = CovenantRoleFactory(speed_rank=3)

    def _make_encounter(
        self,
        opponent_tiers: tuple[str, ...] = (OpponentTier.MOOK,),
    ) -> tuple:
        encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
        opponents = [
            CombatOpponentFactory(encounter=encounter, tier=tier) for tier in opponent_tiers
        ]
        return encounter, opponents

    def _add_pc(self, encounter, role=None) -> CombatParticipant:
        sheet = CharacterSheetFactory()
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        return CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
            covenant_role=role,
        )

    def _seed_config(self, **overrides) -> FleeConfig:
        FleeConfig.objects.filter(pk=1).delete()
        defaults = {
            "check_type": CheckTypeFactory(),
            "base_difficulty": self.BASE_DIFFICULTY,
            "cover_bonus": self.COVER_BONUS,
        }
        defaults.update(overrides)
        return FleeConfig.objects.create(pk=1, **defaults)

    def _partial_pool_with_condition(self, success_level: int) -> tuple:
        """Build a pool with one consequence at the given tier that applies a condition."""
        tier_outcome = CheckOutcomeFactory(
            name=f"FleeTier{success_level}", success_level=success_level
        )
        condition_template = ConditionTemplateFactory(
            name=f"FleeCost{success_level}", has_progression=False
        )
        consequence = ConsequenceFactory(outcome_tier=tier_outcome, character_loss=False)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=condition_template,
            target="self",
        )
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        return pool, consequence, condition_template, tier_outcome

    def test_flee_success_marks_fled_without_consequence(self) -> None:
        """Forced SUCCESS (level 0) → FLED; no ConsequenceOutcome recorded."""
        encounter, _ = self._make_encounter()
        participant = self._add_pc(encounter, role=self.fast_role)
        self._seed_config()
        declare_flee(participant)

        success = CheckOutcomeFactory(name="FleeTestSuccess", success_level=0)
        with force_check_outcome(success):
            resolve_round(encounter)

        participant.refresh_from_db()
        assert participant.status == ParticipantStatus.FLED
        assert ConsequenceOutcome.objects.count() == 0

    def test_flee_partial_escapes_at_a_cost(self) -> None:
        """Forced PARTIAL (level -1) → FLED + pool consequence applied and recorded."""
        encounter, _ = self._make_encounter()
        participant = self._add_pc(encounter, role=self.fast_role)
        pool, consequence, condition_template, partial = self._partial_pool_with_condition(-1)
        self._seed_config(consequence_pool=pool)
        declare_flee(participant)

        with force_check_outcome(partial):
            resolve_round(encounter)

        participant.refresh_from_db()
        assert participant.status == ParticipantStatus.FLED

        # The consequence APPLIED — its condition is active on the character.
        character = participant.character_sheet.character
        assert get_active_conditions(character, condition=condition_template).exists()

        # Provenance recorded against the flee ACTION interaction.
        outcome = ConsequenceOutcome.objects.get()
        assert outcome.character == participant.character_sheet
        assert outcome.pool == pool
        assert outcome.selected_consequence == consequence
        assert outcome.combat_interaction is not None

    def test_flee_failure_stays_active(self) -> None:
        """Forced FAILURE (level -2) → participant stays ACTIVE."""
        encounter, _ = self._make_encounter()
        participant = self._add_pc(encounter, role=self.fast_role)
        self._seed_config()
        declare_flee(participant)

        failure = CheckOutcomeFactory(name="FleeTestFailure", success_level=-2)
        with force_check_outcome(failure):
            resolve_round(encounter)

        participant.refresh_from_db()
        assert participant.status == ParticipantStatus.ACTIVE

    def test_flee_difficulty_uses_max_active_tier_modifier(self) -> None:
        """Difficulty = base + the worst (max) tier modifier among ACTIVE opponents."""
        encounter, _ = self._make_encounter(
            opponent_tiers=(OpponentTier.BOSS, OpponentTier.MOOK),
        )
        participant = self._add_pc(encounter, role=self.fast_role)
        self._seed_config()
        FleeTierModifier.objects.create(tier=OpponentTier.BOSS, difficulty_modifier=30)
        FleeTierModifier.objects.create(tier=OpponentTier.MOOK, difficulty_modifier=10)
        declare_flee(participant)

        success = CheckOutcomeFactory(name="FleeTestDifficulty", success_level=0)
        with force_check_outcome(success) as capture:
            resolve_round(encounter)

        assert capture.target_difficulty == self.BASE_DIFFICULTY + 30

    def test_flee_difficulty_is_base_with_no_active_opponents(self) -> None:
        """Zero ACTIVE opponents → difficulty is base alone (no auto-success term)."""
        encounter, opponents = self._make_encounter()
        opponents[0].status = OpponentStatus.DEFEATED
        opponents[0].save(update_fields=["status"])
        participant = self._add_pc(encounter, role=self.fast_role)
        self._seed_config()
        # A modifier row for the defeated opponent's tier must NOT contribute.
        FleeTierModifier.objects.create(tier=OpponentTier.MOOK, difficulty_modifier=10)
        declare_flee(participant)

        success = CheckOutcomeFactory(name="FleeTestNoOpponents", success_level=0)
        with force_check_outcome(success) as capture:
            resolve_round(encounter)

        assert capture.target_difficulty == self.BASE_DIFFICULTY

    def test_flee_cover_adds_bonus_per_covering_ally(self) -> None:
        """Two same-round COVER declarations targeting the fleer add 2 × cover_bonus."""
        encounter, _ = self._make_encounter()
        fleer = self._add_pc(encounter, role=self.fast_role)
        ally_one = self._add_pc(encounter)
        ally_two = self._add_pc(encounter)
        config = self._seed_config()

        declare_cover(ally_one, fleer)
        declare_cover(ally_two, fleer)
        declare_flee(fleer)

        success = CheckOutcomeFactory(name="FleeTestCover", success_level=0)
        forced_result = CheckResult(
            check_type=config.check_type,
            outcome=success,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        with patch(
            "world.checks.consequence_resolution.perform_check",
            return_value=forced_result,
        ) as mock_check:
            resolve_round(encounter)

        mock_check.assert_called_once()
        extra_modifiers = mock_check.call_args.args[3]
        assert extra_modifiers == 2 * self.COVER_BONUS

        fleer.refresh_from_db()
        assert fleer.status == ParticipantStatus.FLED

    def test_successful_flee_protects_from_same_round_npc_action(self) -> None:
        """A fleer who escapes before the NPC acts takes no damage this round."""
        encounter, opponents = self._make_encounter()
        opponent = opponents[0]
        participant = self._add_pc(encounter, role=self.fast_role)
        self._seed_config()

        entry = ThreatPoolEntryFactory(pool=opponent.threat_pool, base_damage=30)
        npc_action = CombatOpponentAction.objects.create(
            opponent=opponent,
            round_number=1,
            threat_entry=entry,
        )
        npc_action.targets.add(participant)
        declare_flee(participant)

        success = CheckOutcomeFactory(name="FleeTestProtection", success_level=0)
        with force_check_outcome(success):
            result = resolve_round(encounter)

        participant.refresh_from_db()
        assert participant.status == ParticipantStatus.FLED

        vitals = CharacterVitals.objects.get(character_sheet=participant.character_sheet)
        assert vitals.health == 100

        npc_outcomes = [o for o in result.action_outcomes if o.entity_type == "npc"]
        assert all(not o.damage_results for o in npc_outcomes)
