"""An ultimate never fails its roll and never mishaps (#4147)."""

import dataclasses
from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.checks.factories import CheckTypeFactory
from world.checks.types import CheckResult
from world.combat.tests.test_combat_technique_resolver import _build_resolver
from world.magic.factories import (
    CharacterAnimaFactory,
    TechniqueFactory,
    UltimateTechniqueFactory,
)
from world.magic.services.techniques import use_technique
from world.magic.services.ultimates import floor_ultimate_check
from world.mechanics.factories import CharacterEngagementFactory
from world.traits.factories import CheckOutcomeFactory


def _result(outcome) -> CheckResult:
    return CheckResult(
        check_type=CheckTypeFactory(),
        outcome=outcome,
        chart=None,
        roller_rank=None,
        target_rank=None,
        rank_difference=0,
        trait_points=7,
        aspect_bonus=0,
        total_points=7,
    )


class FloorUltimateCheckTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.fail = CheckOutcomeFactory(name="UNF fail", success_level=-1)
        cls.low = CheckOutcomeFactory(name="UNF low", success_level=1)
        cls.high = CheckOutcomeFactory(name="UNF high", success_level=3)
        cls.ultimate = UltimateTechniqueFactory()
        cls.plain = TechniqueFactory()

    def test_failed_ultimate_raised_to_lowest_success(self) -> None:
        floored = floor_ultimate_check(_result(self.fail), self.ultimate)
        assert floored.outcome == self.low
        assert floored.trait_points == 7

    def test_non_ultimate_unchanged(self) -> None:
        result = _result(self.fail)
        assert floor_ultimate_check(result, self.plain) is result

    def test_ultimate_success_unchanged(self) -> None:
        result = _result(self.high)
        assert floor_ultimate_check(result, self.ultimate) is result


class CombatUltimateNeverFailsTests(TestCase):
    def test_forced_failure_lands_as_success(self) -> None:
        fail = CheckOutcomeFactory(name="UNF cfail", success_level=-1)
        low = CheckOutcomeFactory(name="UNF clow", success_level=1)
        resolver = _build_resolver()
        technique = resolver.action.focused_action
        technique.is_ultimate = True
        forced = _result(fail)
        resolver = dataclasses.replace(resolver, offense_check_fn=MagicMock(return_value=forced))
        assert resolver._roll_check().outcome == low


class UltimateNeverMishapsTests(TestCase):
    def _cast(self, technique):
        anima = CharacterAnimaFactory(current=20, maximum=20)
        CharacterEngagementFactory(character=anima.character)
        with patch("world.magic.services.techniques.select_mishap_pool") as pool:
            pool.return_value = None
            result = use_technique(
                character=anima.character.character,
                technique=technique,
                resolve_fn=MagicMock(return_value="resolved"),
            )
        return result, pool

    def test_ultimate_over_control_has_no_mishap(self) -> None:
        technique = UltimateTechniqueFactory(intensity=15, control=5, anima_cost=5)
        result, pool = self._cast(technique)
        assert result.mishap is None
        pool.assert_not_called()

    def test_non_ultimate_over_control_still_rolls_mishap(self) -> None:
        technique = TechniqueFactory(intensity=15, control=5, anima_cost=5)
        _, pool = self._cast(technique)
        pool.assert_called_once_with(10)
