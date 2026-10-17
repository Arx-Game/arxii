"""The fatigue-cost lever (#4394) at the action pipeline."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.fatigue.action_pipeline import execute_action_with_fatigue
from world.fatigue.constants import ActionCategory, EffortLevel
from world.fatigue.models import FatiguePool
from world.fatigue.services import get_or_create_fatigue_pool
from world.fatigue.tests import setup_stat
from world.mechanics.constants import FATIGUE_COST_CATEGORY_NAME, FATIGUE_COST_TARGET_NAME
from world.mechanics.test_helpers import grant_lever
from world.traits.models import TraitCategory


class FatigueCostLeverTests(TestCase):
    def setUp(self) -> None:
        FatiguePool.flush_instance_cache()
        self.sheet = CharacterSheetFactory()
        character = self.sheet.character
        setup_stat(character, "stamina", 30, TraitCategory.PHYSICAL)
        setup_stat(character, "willpower", 20, TraitCategory.META)

    def _act(self, base: int = 10) -> int:
        result = execute_action_with_fatigue(
            self.sheet, ActionCategory.PHYSICAL, base, EffortLevel.MEDIUM
        )
        return result.fatigue_applied

    def test_without_a_lever_the_cost_is_the_base(self) -> None:
        assert self._act() == 10
        assert get_or_create_fatigue_pool(self.sheet).get_current("physical") == 10

    def test_a_tireless_row_pays_nine_of_ten(self) -> None:
        grant_lever(self.sheet, FATIGUE_COST_CATEGORY_NAME, FATIGUE_COST_TARGET_NAME, -10)
        assert self._act() == 9
        assert get_or_create_fatigue_pool(self.sheet).get_current("physical") == 9

    def test_an_action_is_never_free(self) -> None:
        grant_lever(self.sheet, FATIGUE_COST_CATEGORY_NAME, FATIGUE_COST_TARGET_NAME, -100)
        assert self._act() == 1
