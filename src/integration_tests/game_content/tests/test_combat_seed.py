"""Tests for seed_penetration_contest() (#767)."""

from django.test import TestCase

from integration_tests.game_content.combat import seed_penetration_contest
from world.combat.constants import PENETRATION_CHECK_TYPE_NAME
from world.combat.services import get_penetration_check_type
from world.conditions.models import PenetrationOutcomeFactor
from world.mechanics.models import ModifierTarget


class SeedPenetrationContestTests(TestCase):
    def test_seeds_full_contest_content(self) -> None:
        result = seed_penetration_contest()

        # CheckType resolvable the way the resolver resolves it (would raise
        # CheckType.DoesNotExist in an unseeded game).
        check_type = get_penetration_check_type()
        self.assertEqual(result.check_type, check_type)
        self.assertEqual(check_type.traits.count(), 2)

        # Factor ladder authored (4 rungs, bounce → overpenetration).
        self.assertEqual(PenetrationOutcomeFactor.objects.count(), 4)
        self.assertEqual(len(result.factors), 4)

        # Check-scoped ModifierTarget linked to the CheckType.
        self.assertEqual(result.modifier_target.target_check_type, check_type)
        self.assertEqual(ModifierTarget.objects.filter(name=PENETRATION_CHECK_TYPE_NAME).count(), 1)

    def test_idempotent(self) -> None:
        first = seed_penetration_contest()
        second = seed_penetration_contest()
        self.assertEqual(first.check_type.pk, second.check_type.pk)
        self.assertEqual(first.modifier_target.pk, second.modifier_target.pk)
        self.assertEqual(PenetrationOutcomeFactor.objects.count(), 4)
