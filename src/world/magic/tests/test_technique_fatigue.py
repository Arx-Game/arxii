"""Integration tests for fatigue accrual from technique use (#624)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import StrainConfigFactory
from world.fatigue.constants import ActionCategory
from world.fatigue.models import FatiguePool
from world.fatigue.services import get_or_create_fatigue_pool
from world.magic.factories import TechniqueFactory, wire_audere_power_multipliers
from world.magic.models import CharacterAnima
from world.mechanics.factories import (
    CharacterEngagementFactory,
    FatigueCollapseImmunePropertyFactory,
)


def _setup_anima(character, current=20, maximum=20):
    CharacterAnima.objects.update_or_create(
        character=character,
        defaults={"current": current, "maximum": maximum},
    )


class TechniqueFatigueAccrualTests(TestCase):
    """Fatigue is accrued to the correct pool when use_technique fires."""

    @classmethod
    def setUpTestData(cls):
        cls.config = StrainConfigFactory()  # base=25, strain=50

    def setUp(self):
        super().setUp()
        FatiguePool.flush_instance_cache()
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        # Engagement suppresses social-safety +10 control bonus, so
        # effective_cost = max(anima_cost - 0, 0) = anima_cost (intensity=control=1).
        CharacterEngagementFactory(character=self.character)
        self.technique = TechniqueFactory(
            action_category=ActionCategory.PHYSICAL,
            anima_cost=8,
        )
        _setup_anima(self.character, current=20, maximum=20)

    def _run_technique(self, strain_commitment=0):
        from world.magic.services.techniques import use_technique

        resolve_fn = MagicMock(return_value=MagicMock())
        use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=resolve_fn,
            confirm_soulfray_risk=True,
            check_result=None,
            targets=[],
            strain_commitment=strain_commitment,
        )

    def test_physical_technique_accrues_physical_fatigue(self):
        """Casting a physical technique adds fatigue to the physical pool."""
        self._run_technique(strain_commitment=0)
        pool = get_or_create_fatigue_pool(self.sheet)
        # intensity=1, control=1, no engagement modifiers → effective_cost=8
        # 8 base, 0 strain → (8*25 + 0*50) // 100 = 2
        self.assertEqual(pool.get_current(ActionCategory.PHYSICAL), 2)

    def test_zero_fatigue_on_zero_anima_cost(self):
        """A zero-cost cast accrues no fatigue."""
        from world.magic.types import AnimaCostResult

        zero_cost = AnimaCostResult(
            effective_cost=0, deficit=0, base_cost=8, control_delta=0, current_anima=20
        )
        with patch(
            "world.magic.services.techniques.calculate_effective_anima_cost",
            return_value=zero_cost,
        ):
            self._run_technique()
        pool = get_or_create_fatigue_pool(self.sheet)
        self.assertEqual(pool.get_current(ActionCategory.PHYSICAL), 0)


class TechniqueFatigueImmunityTests(TestCase):
    """Characters in Audere/Audere Majora skip the collapse check."""

    @classmethod
    def setUpTestData(cls):
        cls.config = StrainConfigFactory()
        FatigueCollapseImmunePropertyFactory()
        cls.audere_template, _ = wire_audere_power_multipliers()

    def setUp(self):
        super().setUp()
        FatiguePool.flush_instance_cache()
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        # Engagement suppresses social-safety +10 control bonus so effective_cost > 0.
        CharacterEngagementFactory(character=self.character)
        _setup_anima(self.character, current=20, maximum=20)

    def test_audere_character_passes_immune_flag_true(self):
        """When character has Audere condition, immune_to_fatigue_collapse=True is passed."""
        from world.conditions.models import ConditionInstance

        ConditionInstance.objects.create(
            target=self.character,
            condition=self.audere_template,
        )
        technique = TechniqueFactory(action_category=ActionCategory.PHYSICAL, anima_cost=4)
        with patch("world.fatigue.services.apply_technique_fatigue") as mock_fatigue:
            mock_fatigue.return_value = 1
            from world.magic.services.techniques import use_technique

            resolve_fn = MagicMock(return_value=MagicMock())
            use_technique(
                character=self.character,
                technique=technique,
                resolve_fn=resolve_fn,
                confirm_soulfray_risk=True,
                check_result=None,
                targets=[],
                strain_commitment=0,
            )
        mock_fatigue.assert_called_once()
        call_kwargs = mock_fatigue.call_args
        self.assertTrue(call_kwargs.kwargs.get("immune_to_fatigue_collapse"))
