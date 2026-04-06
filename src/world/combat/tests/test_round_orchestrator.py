"""Tests for the round resolution orchestrator."""

from unittest.mock import MagicMock

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    ENTITY_TYPE_PC,
    EncounterStatus,
    OpponentStatus,
    OpponentTier,
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
)
from world.combat.services import resolve_round, upgrade_action_to_combo
from world.magic.factories import EffectTypeFactory, GiftFactory, TechniqueFactory


class ResolveRoundBasicTests(TestCase):
    """Basic round orchestrator tests — PCs attack mooks."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect_attack = EffectTypeFactory(name="Attack", base_power=20)
        cls.gift = GiftFactory()

    def _setup_encounter(self):
        """Create a simple encounter: 1 PC, 1 mook, declaration phase."""
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
            health=100,
            max_health=100,
        )
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_attack,
        )
        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category="physical",
            focused_action=technique,
            focused_target=opponent,
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
        """PC's action deals damage to the opponent."""
        encounter, _participant, opponent, _action, _npc_action = self._setup_encounter()

        resolve_round(encounter)

        opponent.refresh_from_db()
        # base_power is 20, mook has 0 soak, so should take 20 damage
        self.assertEqual(opponent.health, 30)  # 50 - 20

    def test_npc_deals_damage_without_check_type(self) -> None:
        """Without defense_check_type, full base damage is applied."""
        encounter, participant, _opponent, _action, _npc_action = self._setup_encounter()

        resolve_round(encounter)

        participant.refresh_from_db()
        # NPC base_damage is 30, applied directly (no defense check)
        self.assertEqual(participant.health, 70)  # 100 - 30

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
            health=100,
            max_health=100,
        )
        # Attack with base_power 20 > opponent health 10
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_attack,
        )
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category="physical",
            focused_action=technique,
            focused_target=opponent,
        )

        result = resolve_round(encounter)

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
            health=100,
            max_health=100,
            base_speed_rank=5,
        )
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
            focused_category="physical",
            focused_action=technique,
            focused_target=opponent,
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
        cls.effect_attack = EffectTypeFactory(name="Attack", base_power=20)
        cls.gift = GiftFactory()

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
            health=200,
            max_health=200,
        )
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_attack,
        )
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category="physical",
            focused_action=technique,
            focused_target=opponent,
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

        resolve_round(
            encounter,
            defense_check_type=mock_check_type,
            defense_check_fn=mock_check,
        )

        participant.refresh_from_db()
        # base_damage 100, partial success → 50 damage
        # PC also took the attack, but PC attacked the mook first (rank 20 vs 15)
        # Actually, PC has default rank 20 and NPC has rank 15, so NPC resolves first.
        # NPC deals 50 to PC, then PC deals 20 to mook.
        self.assertEqual(participant.health, 150)  # 200 - 50


class ResolveRoundBossPhaseTests(TestCase):
    """Tests for boss phase transitions during round resolution."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect_attack = EffectTypeFactory(name="Attack", base_power=200)
        cls.gift = GiftFactory()

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
            health=500,
            max_health=500,
            base_speed_rank=1,
        )
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_attack,
        )
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category="physical",
            focused_action=technique,
            focused_target=boss,
        )

        result = resolve_round(encounter)

        boss.refresh_from_db()
        # 200 damage → health 300/500 = 60%, below 70% trigger
        self.assertEqual(boss.current_phase, 2)
        self.assertEqual(boss.threat_pool, pool_p2)
        self.assertEqual(boss.soak_value, 50)
        self.assertEqual(len(result.phase_transitions), 1)
