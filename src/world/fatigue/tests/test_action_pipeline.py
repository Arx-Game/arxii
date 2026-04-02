"""Tests for action fatigue cost pipeline."""

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.fatigue.action_pipeline import execute_action_with_fatigue
from world.fatigue.constants import (
    EFFORT_COST_MULTIPLIER,
    EffortLevel,
    FatigueCategory,
    FatigueZone,
)
from world.fatigue.models import FatiguePool
from world.fatigue.services import get_or_create_fatigue_pool
from world.traits.factories import CharacterTraitValueFactory, StatTraitFactory
from world.traits.models import TraitCategory


def _setup_stat(character, stat_name, internal_value, category=TraitCategory.PHYSICAL):
    """Helper to create a stat trait and assign a value to a character."""
    trait = StatTraitFactory(name=stat_name, category=category)
    CharacterTraitValueFactory(character=character, trait=trait, value=internal_value)
    if hasattr(character, "traits") and character.traits.initialized:
        character.traits.clear_cache()


class ExecuteActionBasicTests(TestCase):
    """Tests for basic fatigue application through the action pipeline."""

    def setUp(self):
        FatiguePool.flush_instance_cache()

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        char = cls.sheet.character
        _setup_stat(char, "stamina", 30, TraitCategory.PHYSICAL)
        _setup_stat(char, "willpower", 20, TraitCategory.META)

    def test_action_applies_fatigue_cost(self):
        """Normal effort applies full fatigue cost."""
        result = execute_action_with_fatigue(
            self.sheet, FatigueCategory.PHYSICAL, 10, EffortLevel.NORMAL
        )
        assert result.fatigue_applied == 10

        pool = get_or_create_fatigue_pool(self.sheet)
        assert pool.get_current("physical") == 10

    def test_halfhearted_applies_reduced_cost(self):
        """Halfhearted effort applies 30% fatigue cost."""
        result = execute_action_with_fatigue(
            self.sheet, FatigueCategory.PHYSICAL, 10, EffortLevel.HALFHEARTED
        )
        expected = int(10 * EFFORT_COST_MULTIPLIER[EffortLevel.HALFHEARTED])
        assert result.fatigue_applied == expected

    def test_all_out_applies_double_cost(self):
        """All-out effort applies 200% fatigue cost."""
        result = execute_action_with_fatigue(
            self.sheet, FatigueCategory.PHYSICAL, 10, EffortLevel.ALL_OUT
        )
        assert result.fatigue_applied == 20

    def test_action_without_check_fn(self):
        """Action without check_fn still applies fatigue and returns None check_result."""
        result = execute_action_with_fatigue(
            self.sheet, FatigueCategory.PHYSICAL, 5, EffortLevel.NORMAL
        )
        assert result.check_result is None
        assert result.fatigue_applied == 5

    def test_action_with_check_fn(self):
        """Action with check_fn passes effort modifier and fatigue penalty."""
        captured_args = {}

        def mock_check(effort_mod, fatigue_pen):
            captured_args["effort_mod"] = effort_mod
            captured_args["fatigue_pen"] = fatigue_pen
            return "check_passed"

        result = execute_action_with_fatigue(
            self.sheet,
            FatigueCategory.PHYSICAL,
            5,
            EffortLevel.ALL_OUT,
            check_fn=mock_check,
        )
        assert result.check_result == "check_passed"
        assert captured_args["effort_mod"] == 2  # ALL_OUT modifier
        assert captured_args["fatigue_pen"] == 0  # FRESH zone, no penalty

    def test_result_contains_effort_level(self):
        """ActionResult includes the effort level used."""
        result = execute_action_with_fatigue(
            self.sheet, FatigueCategory.PHYSICAL, 5, EffortLevel.HALFHEARTED
        )
        assert result.effort_level == EffortLevel.HALFHEARTED

    def test_result_contains_fatigue_zone(self):
        """ActionResult includes fatigue zone after cost applied."""
        result = execute_action_with_fatigue(
            self.sheet, FatigueCategory.PHYSICAL, 5, EffortLevel.NORMAL
        )
        assert result.fatigue_zone == FatigueZone.FRESH


class ExecuteActionCollapseTests(TestCase):
    """Tests for collapse risk through the action pipeline."""

    def setUp(self):
        FatiguePool.flush_instance_cache()

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        char = cls.sheet.character
        _setup_stat(char, "stamina", 30, TraitCategory.PHYSICAL)
        _setup_stat(char, "willpower", 20, TraitCategory.META)

    def _set_near_overexerted(self):
        """Put character near overexerted threshold. Capacity = 36, 81% = ~29."""
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.set_current("physical", 28)
        pool.save()

    def test_collapse_triggers_at_overexerted(self):
        """Normal effort triggers collapse when action pushes into overexerted zone."""
        self._set_near_overexerted()
        # Adding 5 -> 33, which is ~92% of 36 capacity = overexerted
        result = execute_action_with_fatigue(
            self.sheet, FatigueCategory.PHYSICAL, 5, EffortLevel.NORMAL
        )
        assert result.collapse_triggered is True

    def test_halfhearted_never_triggers_collapse(self):
        """Halfhearted effort never triggers collapse even when overexerted."""
        self._set_near_overexerted()
        result = execute_action_with_fatigue(
            self.sheet, FatigueCategory.PHYSICAL, 5, EffortLevel.HALFHEARTED
        )
        assert result.collapse_triggered is False
        assert result.collapsed is False

    def test_passes_endurance_no_collapse(self):
        """Passing endurance check means no collapse."""
        self._set_near_overexerted()
        with patch("world.fatigue.action_pipeline.attempt_endurance_check", return_value=True):
            result = execute_action_with_fatigue(
                self.sheet, FatigueCategory.PHYSICAL, 5, EffortLevel.NORMAL
            )
        assert result.collapse_triggered is True
        assert result.collapsed is False
        assert result.powered_through is False

    def test_fails_endurance_powers_through(self):
        """Failing endurance but passing power through: powered_through=True with strain."""
        self._set_near_overexerted()
        with (
            patch("world.fatigue.action_pipeline.attempt_endurance_check", return_value=False),
            patch("world.fatigue.action_pipeline.attempt_power_through", return_value=(True, 3)),
        ):
            result = execute_action_with_fatigue(
                self.sheet, FatigueCategory.PHYSICAL, 5, EffortLevel.NORMAL
            )
        assert result.collapse_triggered is True
        assert result.collapsed is False
        assert result.powered_through is True
        assert result.strain_damage == 3

    def test_fails_both_collapses(self):
        """Failing both endurance and power through: collapsed=True."""
        self._set_near_overexerted()
        with (
            patch("world.fatigue.action_pipeline.attempt_endurance_check", return_value=False),
            patch("world.fatigue.action_pipeline.attempt_power_through", return_value=(False, 2)),
        ):
            result = execute_action_with_fatigue(
                self.sheet, FatigueCategory.PHYSICAL, 5, EffortLevel.NORMAL
            )
        assert result.collapse_triggered is True
        assert result.collapsed is True
        assert result.powered_through is False
        assert result.strain_damage == 2

    def test_fresh_zone_no_collapse(self):
        """Actions in fresh zone do not trigger collapse."""
        result = execute_action_with_fatigue(
            self.sheet, FatigueCategory.PHYSICAL, 5, EffortLevel.ALL_OUT
        )
        assert result.collapse_triggered is False
        assert result.collapsed is False
