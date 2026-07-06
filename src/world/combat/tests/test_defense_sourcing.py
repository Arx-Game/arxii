"""Tests for defense check type sourced from ThreatPoolEntry (#1994)."""

from unittest.mock import MagicMock

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponentAction
from world.combat.services import _resolve_npc_action
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


class DefenseCheckSourcingTests(TestCase):
    """When the external defense_check_type param is None, source it from the
    threat entry's defense_check_type FK (#1994).
    """

    def setUp(self) -> None:
        from world.checks.models import CheckCategory, CheckType

        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        self.pool = ThreatPoolFactory()
        self.sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.sheet,
        )
        CharacterVitals.objects.create(character_sheet=self.sheet, health=200, max_health=200)
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter,
            threat_pool=self.pool,
        )
        # Create a real CheckType for the FK (MagicMock can't be assigned to a FK).
        category = CheckCategory.objects.create(name="test-category-src")
        self.check_type = CheckType.objects.create(name="test-defense-src", category=category)

    def _make_action(self, entry):
        action = CombatOpponentAction.objects.create(
            opponent=self.opponent,
            round_number=1,
            threat_entry=entry,
        )
        action.targets.add(self.participant)
        return action

    def test_threat_entry_defense_check_used_when_param_is_none(self):
        """When defense_check_type=None (production), the threat entry's FK
        is sourced — resolve_npc_attack is called with the entry's CheckType.
        """
        entry = ThreatPoolEntryFactory(
            pool=self.pool, base_damage=100, defense_check_type=self.check_type
        )
        action = self._make_action(entry)

        mock_fn = MagicMock()
        mock_result = MagicMock()
        mock_result.success_level = 2  # full dodge
        mock_fn.return_value = mock_result

        _resolve_npc_action(
            self.opponent,
            action,
            defense_check_type=None,
            defense_check_fn=mock_fn,
        )
        # mock_fn was called → resolve_npc_attack fired with the entry's CheckType
        self.assertTrue(mock_fn.called)
        called_check_type = mock_fn.call_args[0][1]
        self.assertEqual(called_check_type, self.check_type)

    def test_external_param_overrides_threat_entry(self):
        """When a non-None defense_check_type is passed (tests), it takes
        precedence over the threat entry's FK.
        """
        from world.checks.models import CheckCategory, CheckType

        category2 = CheckCategory.objects.create(name="test-category-override")
        override_ct = CheckType.objects.create(name="override-defense", category=category2)
        entry = ThreatPoolEntryFactory(
            pool=self.pool, base_damage=100, defense_check_type=self.check_type
        )
        action = self._make_action(entry)

        mock_fn = MagicMock()
        mock_result = MagicMock()
        mock_result.success_level = 2
        mock_fn.return_value = mock_result

        _resolve_npc_action(
            self.opponent,
            action,
            defense_check_type=override_ct,
            defense_check_fn=mock_fn,
        )
        # The override was used, not the entry's CheckType
        called_check_type = mock_fn.call_args[0][1]
        self.assertEqual(called_check_type, override_ct)

    def test_flat_damage_when_neither_param_nor_entry_set(self):
        """When both param and entry FK are None, flat base_damage applies
        (backward-compatible — today's production behavior). Health decreases
        by base_damage.
        """
        entry = ThreatPoolEntryFactory(pool=self.pool, base_damage=50, defense_check_type=None)
        action = self._make_action(entry)

        _resolve_npc_action(
            self.opponent,
            action,
            defense_check_type=None,
            defense_check_fn=MagicMock(),
        )
        vitals = CharacterVitals.objects.get(character_sheet=self.sheet)
        self.assertEqual(vitals.health, 150)  # 200 - 50
