"""Tests for defensive check integration in combat."""

from unittest.mock import MagicMock

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    DEFENSE_CRITICAL_MULTIPLIER,
    DEFENSE_FULL_MULTIPLIER,
    DEFENSE_REDUCED_MULTIPLIER,
    EncounterStatus,
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
    _damage_multiplier_for_success,
    resolve_npc_attack,
)
from world.vitals.constants import CharacterStatus
from world.vitals.models import CharacterVitals


class DamageMultiplierTests(TestCase):
    """Tests for _damage_multiplier_for_success."""

    def test_great_success_no_damage(self) -> None:
        self.assertEqual(_damage_multiplier_for_success(2), 0.0)
        self.assertEqual(_damage_multiplier_for_success(3), 0.0)

    def test_partial_success_reduced(self) -> None:
        self.assertEqual(
            _damage_multiplier_for_success(1),
            DEFENSE_REDUCED_MULTIPLIER,
        )

    def test_failure_full_damage(self) -> None:
        self.assertEqual(
            _damage_multiplier_for_success(0),
            DEFENSE_FULL_MULTIPLIER,
        )

    def test_critical_failure_extra(self) -> None:
        self.assertEqual(
            _damage_multiplier_for_success(-1),
            DEFENSE_CRITICAL_MULTIPLIER,
        )
        self.assertEqual(
            _damage_multiplier_for_success(-3),
            DEFENSE_CRITICAL_MULTIPLIER,
        )


class ResolveNpcAttackTests(TestCase):
    """Tests for resolve_npc_attack with mocked perform_check."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        pool = ThreatPoolFactory()
        cls.entry = ThreatPoolEntryFactory(pool=pool, base_damage=100)
        cls.opponent = CombatOpponentFactory(
            encounter=cls.encounter,
            threat_pool=pool,
        )
        cls.sheet = CharacterSheetFactory()
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=cls.sheet,
        )
        CharacterVitals.objects.create(
            character_sheet=cls.sheet,
            health=200,
            max_health=200,
            status=CharacterStatus.ALIVE,
        )
        cls.npc_action = CombatOpponentAction.objects.create(
            opponent=cls.opponent,
            round_number=1,
            threat_entry=cls.entry,
        )
        cls.npc_action.targets.add(cls.participant)
        cls.mock_check_type = MagicMock()

    def setUp(self) -> None:
        # Reset vitals health before each test since apply_damage modifies it
        vitals = CharacterVitals.objects.get(character_sheet=self.sheet)
        vitals.health = 200
        vitals.max_health = 200
        vitals.status = CharacterStatus.ALIVE
        vitals.save()

    def _make_mock_check(self, success_level: int) -> MagicMock:
        mock_fn = MagicMock()
        mock_result = MagicMock()
        mock_result.success_level = success_level
        mock_fn.return_value = mock_result
        return mock_fn

    def test_great_success_no_damage(self) -> None:
        mock_fn = self._make_mock_check(success_level=2)
        result = resolve_npc_attack(
            self.npc_action,
            self.participant,
            self.mock_check_type,
            perform_check_fn=mock_fn,
        )
        self.assertEqual(result.final_damage, 0)
        self.assertEqual(result.damage_multiplier, 0.0)

    def test_partial_success_half_damage(self) -> None:
        mock_fn = self._make_mock_check(success_level=1)
        result = resolve_npc_attack(
            self.npc_action,
            self.participant,
            self.mock_check_type,
            perform_check_fn=mock_fn,
        )
        self.assertEqual(result.final_damage, 50)  # 100 * 0.5
        self.assertEqual(result.damage_multiplier, DEFENSE_REDUCED_MULTIPLIER)

    def test_failure_full_damage(self) -> None:
        mock_fn = self._make_mock_check(success_level=0)
        result = resolve_npc_attack(
            self.npc_action,
            self.participant,
            self.mock_check_type,
            perform_check_fn=mock_fn,
        )
        self.assertEqual(result.final_damage, 100)

    def test_critical_failure_extra_damage(self) -> None:
        mock_fn = self._make_mock_check(success_level=-1)
        result = resolve_npc_attack(
            self.npc_action,
            self.participant,
            self.mock_check_type,
            perform_check_fn=mock_fn,
        )
        self.assertEqual(result.final_damage, 150)  # 100 * 1.5

    def test_damage_applies_to_participant(self) -> None:
        """Health is reduced after the attack resolves."""
        mock_fn = self._make_mock_check(success_level=0)
        result = resolve_npc_attack(
            self.npc_action,
            self.participant,
            self.mock_check_type,
            perform_check_fn=mock_fn,
        )
        vitals = CharacterVitals.objects.get(character_sheet=self.sheet)
        self.assertEqual(vitals.health, 200 - result.final_damage)
