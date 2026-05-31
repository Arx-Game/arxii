"""Tests for the round resolution orchestrator."""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from actions.factories import ActionTemplateFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import (
    ENTITY_TYPE_PC,
    ActionCategory,
    EncounterStatus,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ComboDefinitionFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import (
    BossPhase,
    CombatOpponent,
    CombatOpponentAction,
    CombatRoundAction,
    RoundChallengeDeclaration,
)
from world.combat.services import resolve_round, upgrade_action_to_combo
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.covenants.factories import CovenantRoleFactory
from world.fatigue.constants import EffortLevel
from world.fatigue.models import FatiguePool
from world.magic.factories import (
    CharacterAnimaFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.mechanics.constants import CapabilitySourceType
from world.mechanics.factories import (
    ChallengeApproachFactory,
    ChallengeInstanceFactory,
    CharacterEngagementFactory,
)
from world.mechanics.models import CharacterChallengeRecord
from world.mechanics.types import AvailableAction, CapabilitySource
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory
from world.scenes.models import Interaction
from world.traits.factories import CheckOutcomeFactory
from world.vitals.models import CharacterVitals


class ResolveRoundBasicTests(TestCase):
    """Basic round orchestrator tests — PCs attack mooks."""

    @classmethod
    def setUpTestData(cls) -> None:
        from decimal import Decimal

        cls.effect_attack = EffectTypeFactory(name="Attack", base_power=20)
        cls.gift = GiftFactory()
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )

    def _setup_encounter(self):
        """Create a simple encounter: 1 PC, 1 mook, declaration phase.

        Sets up the full magic pipeline requirements (CharacterAnima,
        CharacterEngagement, room location) so tests can pass an
        offense_check_fn to route through resolve_combat_technique.
        """
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        pool = ThreatPoolFactory()
        entry = ThreatPoolEntryFactory(pool=pool, base_damage=30)
        opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            threat_pool=pool,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
        )
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet.character)
        room = ObjectDB.objects.create(
            db_key="TestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        sheet.character.location = room
        sheet.character.save()

        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_attack,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
        )
        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=opponent,
        )
        # NPC action targeting the PC
        npc_action = CombatOpponentAction.objects.create(
            opponent=opponent,
            round_number=1,
            threat_entry=entry,
        )
        npc_action.targets.add(participant)

        return encounter, participant, opponent, action, npc_action

    def test_basic_round_resolves(self) -> None:
        """A round with 1 PC and 1 NPC resolves successfully."""
        encounter, _participant, _opponent, _action, _npc_action = self._setup_encounter()

        result = resolve_round(encounter)

        self.assertEqual(result.round_number, 1)
        self.assertGreater(len(result.action_outcomes), 0)
        encounter.refresh_from_db()
        # Should transition to BETWEEN_ROUNDS or COMPLETED
        self.assertIn(
            encounter.status,
            [EncounterStatus.BETWEEN_ROUNDS, EncounterStatus.COMPLETED],
        )

    def test_pc_deals_damage(self) -> None:
        """PC's action deals damage to the opponent via the magic pipeline."""
        encounter, _participant, opponent, _action, _npc_action = self._setup_encounter()

        def mock_check_fn(*args, **kwargs):  # type: ignore[no-untyped-def]
            return MagicMock(success_level=2)

        resolve_round(
            encounter,
            offense_check_fn=mock_check_fn,
        )

        opponent.refresh_from_db()
        # base_power is 20, mook has 0 soak, so should take 20 damage
        self.assertEqual(opponent.health, 30)  # 50 - 20

    def test_npc_deals_damage_without_check_type(self) -> None:
        """Without defense_check_type, full base damage is applied."""
        encounter, participant, _opponent, _action, _npc_action = self._setup_encounter()

        resolve_round(encounter)

        vitals = CharacterVitals.objects.get(character_sheet=participant.character_sheet)
        # NPC base_damage is 30, applied directly (no defense check)
        self.assertEqual(vitals.health, 70)  # 100 - 30

    def test_pc_spell_deals_damage_when_check_type_sourced_from_template(self) -> None:
        """Regression: view calls resolve_round with no offense_check_type.

        When the production view calls resolve_round(encounter) without
        offense_check_type, _resolve_pc_action silently skips technique
        resolution (the `if offense_check_type is not None:` gate in
        services.py) and the opponent takes zero damage.  This test reproduces
        that call shape and asserts the correct outcome so that the fix is
        confirmed when the test goes green.
        """
        encounter, _participant, opponent, action, _npc = self._setup_encounter()
        template = ActionTemplateFactory(check_type=CheckTypeFactory())
        action.focused_action.action_template = template
        action.focused_action.save(update_fields=["action_template"])

        def mock_check_fn(*args, **kwargs):  # type: ignore[no-untyped-def]
            return MagicMock(success_level=2)

        # Called exactly as the production view calls it: NO offense_check_type.
        resolve_round(encounter, offense_check_fn=mock_check_fn)

        opponent.refresh_from_db()
        self.assertEqual(opponent.health, 30)  # 50 - 20 (damaging technique)

    def test_wrong_status_raises(self) -> None:
        """Resolving a non-DECLARING encounter raises ValueError."""
        encounter = CombatEncounterFactory(
            status=EncounterStatus.BETWEEN_ROUNDS,
            round_number=1,
        )
        with self.assertRaises(ValueError):
            resolve_round(encounter)

    def test_encounter_completes_when_opponent_defeated(self) -> None:
        """Encounter completes when all opponents are defeated."""
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        pool = ThreatPoolFactory()
        opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=10,
            max_health=10,
            threat_pool=pool,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
        )
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet.character)
        room = ObjectDB.objects.create(
            db_key="TestRoomComplete",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        sheet.character.location = room
        sheet.character.save()

        # Attack with base_power 20 > opponent health 10
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_attack,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
        )
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=opponent,
        )

        def mock_check_fn(*args, **kwargs):  # type: ignore[no-untyped-def]
            return MagicMock(success_level=2)

        result = resolve_round(
            encounter,
            offense_check_fn=mock_check_fn,
        )

        self.assertTrue(result.encounter_completed)
        encounter.refresh_from_db()
        self.assertEqual(encounter.status, EncounterStatus.COMPLETED)
        opponent.refresh_from_db()
        self.assertEqual(opponent.status, OpponentStatus.DEFEATED)


class ResolveRoundComboTests(TestCase):
    """Tests for round resolution with combo upgrades."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect_attack = EffectTypeFactory(name="Attack", base_power=20)
        cls.effect_defense = EffectTypeFactory(name="Defense", base_power=10)
        cls.gift = GiftFactory()

    def test_combo_deals_bonus_damage_bypassing_soak(self) -> None:
        """A combo-upgraded action deals bonus damage that bypasses soak."""
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        pool = ThreatPoolFactory()
        opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            health=500,
            max_health=500,
            soak_value=80,
            threat_pool=pool,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
            covenant_role=CovenantRoleFactory(speed_rank=5),
        )
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_attack,
        )
        combo = ComboDefinitionFactory(
            bypass_soak=True,
            bonus_damage=100,
        )
        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=opponent,
        )
        upgrade_action_to_combo(action, combo)

        result = resolve_round(encounter)

        opponent.refresh_from_db()
        # Combo with bypass_soak=True, bonus_damage=100. Boss soak=80 but bypassed.
        # So 100 damage goes through.
        self.assertEqual(opponent.health, 400)  # 500 - 100

        # Verify combo was noted in the outcome
        pc_outcomes = [o for o in result.action_outcomes if o.entity_type == ENTITY_TYPE_PC]
        self.assertEqual(len(pc_outcomes), 1)
        self.assertEqual(pc_outcomes[0].combo_used, combo)


class ResolveRoundDefenseCheckTests(TestCase):
    """Tests for round resolution with defensive checks."""

    @classmethod
    def setUpTestData(cls) -> None:
        from decimal import Decimal

        cls.effect_attack = EffectTypeFactory(name="Attack", base_power=20)
        cls.gift = GiftFactory()
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )

    def test_defense_check_reduces_damage(self) -> None:
        """With defense_check_type and a partial success, damage is reduced."""
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        pool = ThreatPoolFactory()
        entry = ThreatPoolEntryFactory(pool=pool, base_damage=100)
        opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            threat_pool=pool,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
        )
        CharacterVitals.objects.create(character_sheet=sheet, health=200, max_health=200)
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet.character)
        room = ObjectDB.objects.create(
            db_key="TestRoomDefense",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        sheet.character.location = room
        sheet.character.save()
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_attack,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
        )
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=opponent,
        )
        npc_action = CombatOpponentAction.objects.create(
            opponent=opponent,
            round_number=1,
            threat_entry=entry,
        )
        npc_action.targets.add(participant)

        # Mock defense check to return partial success (success_level=1 → 50% damage)
        mock_check = MagicMock()
        mock_result = MagicMock()
        mock_result.success_level = 1
        mock_check.return_value = mock_result
        mock_check_type = MagicMock()

        def mock_offense_check_fn(*args, **kwargs):  # type: ignore[no-untyped-def]
            return MagicMock(success_level=2)

        resolve_round(
            encounter,
            defense_check_type=mock_check_type,
            defense_check_fn=mock_check,
            offense_check_fn=mock_offense_check_fn,
        )

        vitals = CharacterVitals.objects.get(character_sheet=sheet)
        # base_damage 100, partial success → 50 damage
        # PC has default rank 20 and NPC has rank 15, so NPC resolves first.
        # NPC deals 50 to PC, then PC deals 20 to mook.
        self.assertEqual(vitals.health, 150)  # 200 - 50


class ResolveRoundBossPhaseTests(TestCase):
    """Tests for boss phase transitions during round resolution."""

    @classmethod
    def setUpTestData(cls) -> None:
        from decimal import Decimal

        cls.effect_attack = EffectTypeFactory(name="Attack", base_power=200)
        cls.gift = GiftFactory()
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )

    def test_boss_phase_advances_during_round(self) -> None:
        """Boss phase transitions when health drops below trigger."""
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        pool_p1 = ThreatPoolFactory(name="Boss Phase 1")
        pool_p2 = ThreatPoolFactory(name="Boss Phase 2")
        boss = CombatOpponent.objects.create(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            name="Dragon",
            health=500,
            max_health=500,
            soak_value=0,
            threat_pool=pool_p1,
        )
        BossPhase.objects.create(
            opponent=boss,
            phase_number=2,
            threat_pool=pool_p2,
            soak_value=50,
            probing_threshold=30,
            health_trigger_percentage=0.7,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
            covenant_role=CovenantRoleFactory(speed_rank=1),
        )
        CharacterVitals.objects.create(character_sheet=sheet, health=500, max_health=500)
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet.character)
        room = ObjectDB.objects.create(
            db_key="TestRoomBoss",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        sheet.character.location = room
        sheet.character.save()

        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_attack,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
        )
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=boss,
        )

        def mock_check_fn(*args, **kwargs):  # type: ignore[no-untyped-def]
            return MagicMock(success_level=2)

        result = resolve_round(
            encounter,
            offense_check_fn=mock_check_fn,
        )

        boss.refresh_from_db()
        # 200 damage → health 300/500 = 60%, below 70% trigger
        self.assertEqual(boss.current_phase, 2)
        self.assertEqual(boss.threat_pool, pool_p2)
        self.assertEqual(boss.soak_value, 50)
        self.assertEqual(len(result.phase_transitions), 1)


class ResolveRoundOffenseCheckTests(TestCase):
    """Tests for PC offensive checks and fatigue during round resolution."""

    @classmethod
    def setUpTestData(cls) -> None:
        from decimal import Decimal

        cls.effect_attack = EffectTypeFactory(name="Attack", base_power=20)
        cls.gift = GiftFactory()
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )

    def _setup_encounter(self) -> tuple:
        """Create encounter: 1 PC, 1 mook, PC action declared."""
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        pool = ThreatPoolFactory()
        opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=500,
            max_health=500,
            threat_pool=pool,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
            covenant_role=CovenantRoleFactory(speed_rank=1),
        )
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet.character)
        room = ObjectDB.objects.create(
            db_key="TestRoomOffense",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        sheet.character.location = room
        sheet.character.save()
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_attack,
            anima_cost=5,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
        )
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_action=technique,
            focused_opponent_target=opponent,
        )
        return encounter, participant, opponent

    def test_pc_miss_deals_no_damage(self) -> None:
        """PC check with success_level=0 deals no damage."""
        encounter, _participant, opponent = self._setup_encounter()

        mock_check = MagicMock()
        mock_result = MagicMock()
        mock_result.success_level = 0
        mock_check.return_value = mock_result

        resolve_round(
            encounter,
            offense_check_fn=mock_check,
        )

        opponent.refresh_from_db()
        # Miss: no damage dealt, health unchanged
        self.assertEqual(opponent.health, 500)

    def test_fatigue_applied_after_action(self) -> None:
        """Fatigue pool increases after PC action resolves."""
        encounter, participant, _opponent = self._setup_encounter()

        # Ensure fatigue pool starts at 0
        pool, _ = FatiguePool.objects.get_or_create(
            character_sheet=participant.character_sheet,
        )
        self.assertEqual(pool.physical_current, 0)

        resolve_round(encounter)

        pool.refresh_from_db()
        # anima_cost=5, medium effort multiplier=1.0 -> cost=5
        self.assertGreater(pool.physical_current, 0)


def _make_dummy_capability_source(capability_id: int = 1) -> CapabilitySource:
    """Build a minimal CapabilitySource for patching get_available_actions."""
    return CapabilitySource(
        capability_name="fire_control",
        capability_id=capability_id,
        value=10,
        source_type=CapabilitySourceType.TECHNIQUE,
        source_name="Test Technique",
        source_id=1,
    )


def _make_available_action(
    challenge_instance_id: int,
    approach_id: int,
    capability_source: CapabilitySource,
) -> AvailableAction:
    """Build a minimal AvailableAction for patching."""
    return AvailableAction(
        application_id=1,
        application_name="Test Application",
        capability_source=capability_source,
        challenge_instance_id=challenge_instance_id,
        challenge_name="Test Challenge",
        approach_id=approach_id,
        check_type_name="test_check",
        display_name="Test Action",
        custom_description="",
    )


class ResolveDeclaredChallengesTests(TestCase):
    """Post-pass: RoundChallengeDeclarations resolve after combat actions."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.check_outcome = CheckOutcomeFactory(name="ChallengeSuccess", success_level=2)

    def _make_mock_check_result(self) -> MagicMock:
        """Return a mock CheckResult with a real CheckOutcome for FK compatibility."""
        result = MagicMock()
        result.outcome = self.check_outcome
        result.success_level = 2
        return result

    def _setup_declaring_encounter(
        self,
    ) -> tuple[object, object]:
        """Create a DECLARING encounter with one ACTIVE participant."""
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
        )
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        return encounter, participant

    def test_challenge_declaration_resolves_and_bridge_row_deleted(self) -> None:
        """Participant with RoundChallengeDeclaration (no CombatRoundAction):
        after resolve_round, CharacterChallengeRecord exists and bridge row deleted.
        """
        encounter, participant = self._setup_declaring_encounter()
        challenge_instance = ChallengeInstanceFactory()
        approach = ChallengeApproachFactory(
            challenge_template=challenge_instance.template,
        )

        RoundChallengeDeclaration.objects.create(
            encounter=encounter,
            round_number=1,
            participant=participant,
            challenge_instance=challenge_instance,
            challenge_approach=approach,
        )

        cap_source = _make_dummy_capability_source()
        available = _make_available_action(
            challenge_instance_id=challenge_instance.pk,
            approach_id=approach.pk,
            capability_source=cap_source,
        )

        with patch(
            "world.combat.services.get_available_actions",
            return_value=[available],
        ):
            with patch(
                "world.mechanics.challenge_resolution.perform_check",
                side_effect=lambda *_a, **_kw: self._make_mock_check_result(),
            ):
                resolve_round(encounter)

        # Bridge row must be deleted
        self.assertFalse(
            RoundChallengeDeclaration.objects.filter(
                encounter=encounter,
                round_number=1,
            ).exists(),
            "RoundChallengeDeclaration should be deleted after resolve_round",
        )

        # CharacterChallengeRecord must be created (resolve_challenge creates it)
        character = participant.character_sheet.character
        self.assertTrue(
            CharacterChallengeRecord.objects.filter(
                character=character,
                challenge_instance=challenge_instance,
            ).exists(),
            "CharacterChallengeRecord should exist after challenge was resolved",
        )

    def test_challenge_outcomes_on_result(self) -> None:
        """resolve_round result carries challenge_outcomes for the resolved declaration."""
        encounter, participant = self._setup_declaring_encounter()
        challenge_instance = ChallengeInstanceFactory()
        approach = ChallengeApproachFactory(
            challenge_template=challenge_instance.template,
        )

        RoundChallengeDeclaration.objects.create(
            encounter=encounter,
            round_number=1,
            participant=participant,
            challenge_instance=challenge_instance,
            challenge_approach=approach,
        )

        cap_source = _make_dummy_capability_source()
        available = _make_available_action(
            challenge_instance_id=challenge_instance.pk,
            approach_id=approach.pk,
            capability_source=cap_source,
        )

        with patch(
            "world.combat.services.get_available_actions",
            return_value=[available],
        ):
            with patch(
                "world.mechanics.challenge_resolution.perform_check",
                side_effect=lambda *_a, **_kw: self._make_mock_check_result(),
            ):
                result = resolve_round(encounter)

        self.assertEqual(len(result.challenge_outcomes), 1)
        self.assertEqual(
            result.challenge_outcomes[0].challenge_instance_id,
            challenge_instance.pk,
        )

    def test_challenge_resolution_broadcasts_outcome_narration(self) -> None:
        """A resolved declared challenge broadcasts a Narrator OUTCOME line (#644).

        The challenge-only participant has no combat action and there is no NPC,
        so the sole OUTCOME interaction is the challenge narration.
        """
        encounter, participant = self._setup_declaring_encounter()
        encounter.scene = SceneFactory()
        encounter.save(update_fields=["scene"])
        challenge_instance = ChallengeInstanceFactory()
        approach = ChallengeApproachFactory(
            challenge_template=challenge_instance.template,
        )

        RoundChallengeDeclaration.objects.create(
            encounter=encounter,
            round_number=1,
            participant=participant,
            challenge_instance=challenge_instance,
            challenge_approach=approach,
        )

        cap_source = _make_dummy_capability_source()
        available = _make_available_action(
            challenge_instance_id=challenge_instance.pk,
            approach_id=approach.pk,
            capability_source=cap_source,
        )

        with patch(
            "world.combat.services.get_available_actions",
            return_value=[available],
        ):
            with patch(
                "world.mechanics.challenge_resolution.perform_check",
                side_effect=lambda *_a, **_kw: self._make_mock_check_result(),
            ):
                resolve_round(encounter)

        outcomes = Interaction.objects.filter(
            mode=InteractionMode.OUTCOME, content__icontains="attempts"
        )
        self.assertEqual(outcomes.count(), 1, "Expected one challenge OUTCOME narration line.")

    def test_two_participants_both_challenges_resolve(self) -> None:
        """Two participants with challenge declarations both resolve post-combat."""
        encounter, participant1 = self._setup_declaring_encounter()
        sheet2 = CharacterSheetFactory()
        participant2 = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet2,
            status=ParticipantStatus.ACTIVE,
        )
        CharacterVitals.objects.create(character_sheet=sheet2, health=100, max_health=100)

        ci1 = ChallengeInstanceFactory()
        approach1 = ChallengeApproachFactory(challenge_template=ci1.template)
        ci2 = ChallengeInstanceFactory()
        approach2 = ChallengeApproachFactory(challenge_template=ci2.template)

        RoundChallengeDeclaration.objects.create(
            encounter=encounter,
            round_number=1,
            participant=participant1,
            challenge_instance=ci1,
            challenge_approach=approach1,
        )
        RoundChallengeDeclaration.objects.create(
            encounter=encounter,
            round_number=1,
            participant=participant2,
            challenge_instance=ci2,
            challenge_approach=approach2,
        )

        cap_source = _make_dummy_capability_source()

        def patched_get_available_actions(
            character: object, location: object, **kwargs: object
        ) -> list[AvailableAction]:
            """Return the appropriate AvailableAction by challenge instance location."""
            if character == participant1.character_sheet.character:
                return [
                    _make_available_action(
                        challenge_instance_id=ci1.pk,
                        approach_id=approach1.pk,
                        capability_source=cap_source,
                    )
                ]
            if character == participant2.character_sheet.character:
                return [
                    _make_available_action(
                        challenge_instance_id=ci2.pk,
                        approach_id=approach2.pk,
                        capability_source=cap_source,
                    )
                ]
            return []

        with patch(
            "world.combat.services.get_available_actions",
            side_effect=patched_get_available_actions,
        ):
            with patch(
                "world.mechanics.challenge_resolution.perform_check",
                side_effect=lambda *_a, **_kw: self._make_mock_check_result(),
            ):
                result = resolve_round(encounter)

        # Both bridge rows deleted
        self.assertFalse(
            RoundChallengeDeclaration.objects.filter(encounter=encounter).exists(),
            "All RoundChallengeDeclarations should be deleted after resolve_round",
        )

        # Both characters resolved
        self.assertTrue(
            CharacterChallengeRecord.objects.filter(
                character=participant1.character_sheet.character,
            ).exists(),
            "Participant 1 challenge should be resolved",
        )
        self.assertTrue(
            CharacterChallengeRecord.objects.filter(
                character=participant2.character_sheet.character,
            ).exists(),
            "Participant 2 challenge should be resolved",
        )

        # Both outcomes on result
        self.assertEqual(len(result.challenge_outcomes), 2)

    def test_combat_action_resolves_before_challenge_post_pass(self) -> None:
        """Combat damage applies independently, challenge post-pass runs after.

        One participant declares a COMBAT action, another declares a CHALLENGE.
        After resolve_round:
        - combat damage is applied to the opponent
        - challenge is resolved (CharacterChallengeRecord exists)
        Both must succeed — demonstrating post-pass runs after combat resolution.
        """
        from decimal import Decimal

        EffectTypeFactory(name="AttackChallenge", base_power=20)
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="FullC"
        )
        gift = GiftFactory()

        encounter, participant_challenge = self._setup_declaring_encounter()

        pool = ThreatPoolFactory()
        opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            threat_pool=pool,
        )
        sheet_combat = CharacterSheetFactory()
        participant_combat = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet_combat,
            status=ParticipantStatus.ACTIVE,
        )
        CharacterVitals.objects.create(character_sheet=sheet_combat, health=100, max_health=100)
        CharacterAnimaFactory(character=sheet_combat.character, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet_combat.character)
        room = ObjectDB.objects.create(
            db_key="TestRoomChalPost",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        sheet_combat.character.location = room
        sheet_combat.character.save()

        effect_attack = EffectTypeFactory(name="AttackChallenge2", base_power=20)
        technique = TechniqueFactory(
            gift=gift,
            effect_type=effect_attack,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
        )
        CombatRoundAction.objects.create(
            participant=participant_combat,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=opponent,
        )

        ci = ChallengeInstanceFactory()
        approach = ChallengeApproachFactory(challenge_template=ci.template)
        RoundChallengeDeclaration.objects.create(
            encounter=encounter,
            round_number=1,
            participant=participant_challenge,
            challenge_instance=ci,
            challenge_approach=approach,
        )

        cap_source = _make_dummy_capability_source()
        available = _make_available_action(
            challenge_instance_id=ci.pk,
            approach_id=approach.pk,
            capability_source=cap_source,
        )

        mock_check_result = self._make_mock_check_result()

        def mock_offense_check(*args: object, **kwargs: object) -> object:
            return mock_check_result

        with patch(
            "world.combat.services.get_available_actions",
            return_value=[available],
        ):
            with patch(
                "world.mechanics.challenge_resolution.perform_check",
                side_effect=lambda *_a, **_kw: mock_check_result,
            ):
                resolve_round(encounter, offense_check_fn=mock_offense_check)

        # Combat damage applied to opponent
        opponent.refresh_from_db()
        self.assertLess(
            opponent.health,
            50,
            "Combat participant should have dealt damage to opponent",
        )

        # Challenge post-pass resolved
        self.assertTrue(
            CharacterChallengeRecord.objects.filter(
                character=participant_challenge.character_sheet.character,
                challenge_instance=ci,
            ).exists(),
            "Challenge participant's resolution record should exist",
        )

    def test_ineligible_declaration_skipped_no_exception(self) -> None:
        """Declaration skipped gracefully when character has no matching capability at resolution.

        get_available_actions returns empty → no CharacterChallengeRecord created,
        no exception raised. Bridge row still deleted after the post-pass.
        """
        encounter, participant = self._setup_declaring_encounter()
        challenge_instance = ChallengeInstanceFactory()
        approach = ChallengeApproachFactory(
            challenge_template=challenge_instance.template,
        )

        RoundChallengeDeclaration.objects.create(
            encounter=encounter,
            round_number=1,
            participant=participant,
            challenge_instance=challenge_instance,
            challenge_approach=approach,
        )

        # get_available_actions returns empty → ineligible
        with patch(
            "world.combat.services.get_available_actions",
            return_value=[],
        ):
            resolve_round(encounter)  # Must not raise

        # Bridge row deleted even on skip
        self.assertFalse(
            RoundChallengeDeclaration.objects.filter(
                encounter=encounter,
                round_number=1,
            ).exists(),
            "Bridge row should be deleted even for skipped (ineligible) declarations",
        )

        # No CharacterChallengeRecord — challenge was skipped
        character = participant.character_sheet.character
        self.assertFalse(
            CharacterChallengeRecord.objects.filter(
                character=character,
                challenge_instance=challenge_instance,
            ).exists(),
            "CharacterChallengeRecord should NOT exist when declaration was skipped",
        )

    def test_ineligible_skip_does_not_block_other_declarations(self) -> None:
        """Ineligible skip for one participant does not prevent others from resolving."""
        encounter, participant_ineligible = self._setup_declaring_encounter()
        sheet2 = CharacterSheetFactory()
        participant_eligible = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet2,
            status=ParticipantStatus.ACTIVE,
        )
        CharacterVitals.objects.create(character_sheet=sheet2, health=100, max_health=100)

        ci_ineligible = ChallengeInstanceFactory()
        approach_ineligible = ChallengeApproachFactory(
            challenge_template=ci_ineligible.template,
        )
        ci_eligible = ChallengeInstanceFactory()
        approach_eligible = ChallengeApproachFactory(
            challenge_template=ci_eligible.template,
        )

        RoundChallengeDeclaration.objects.create(
            encounter=encounter,
            round_number=1,
            participant=participant_ineligible,
            challenge_instance=ci_ineligible,
            challenge_approach=approach_ineligible,
        )
        RoundChallengeDeclaration.objects.create(
            encounter=encounter,
            round_number=1,
            participant=participant_eligible,
            challenge_instance=ci_eligible,
            challenge_approach=approach_eligible,
        )

        cap_source = _make_dummy_capability_source()

        def patched_get_available_actions(
            character: object, location: object, **kwargs: object
        ) -> list[AvailableAction]:
            if character == participant_eligible.character_sheet.character:
                return [
                    _make_available_action(
                        challenge_instance_id=ci_eligible.pk,
                        approach_id=approach_eligible.pk,
                        capability_source=cap_source,
                    )
                ]
            # participant_ineligible gets empty list → skipped
            return []

        with patch(
            "world.combat.services.get_available_actions",
            side_effect=patched_get_available_actions,
        ):
            with patch(
                "world.mechanics.challenge_resolution.perform_check",
                side_effect=lambda *_a, **_kw: self._make_mock_check_result(),
            ):
                resolve_round(encounter)  # Must not raise

        # Ineligible: no record
        self.assertFalse(
            CharacterChallengeRecord.objects.filter(
                character=participant_ineligible.character_sheet.character,
            ).exists(),
        )

        # Eligible: record exists
        self.assertTrue(
            CharacterChallengeRecord.objects.filter(
                character=participant_eligible.character_sheet.character,
            ).exists(),
        )
