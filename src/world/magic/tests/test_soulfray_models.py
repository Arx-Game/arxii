"""Tests for AnimaRitualBudgetAward (#1207)."""

from __future__ import annotations

from django.test import TestCase

from world.magic.models.soulfray import AnimaRitualBudgetAward
from world.traits.factories import CheckOutcomeFactory


class AnimaRitualBudgetAwardTests(TestCase):
    def test_create_and_lookup_by_outcome_tier(self):
        outcome = CheckOutcomeFactory(success_level=2)
        AnimaRitualBudgetAward.objects.create(outcome_tier=outcome, budget=10)
        fetched = AnimaRitualBudgetAward.objects.get(outcome_tier=outcome)
        self.assertEqual(fetched.budget, 10)

    def test_ordered_by_success_level(self):
        crit = CheckOutcomeFactory(success_level=2)
        fail = CheckOutcomeFactory(success_level=-1)
        AnimaRitualBudgetAward.objects.create(outcome_tier=fail, budget=1)
        AnimaRitualBudgetAward.objects.create(outcome_tier=crit, budget=10)
        ordered = list(AnimaRitualBudgetAward.objects.all())
        self.assertEqual(ordered[0].outcome_tier_id, fail.pk)
        self.assertEqual(ordered[1].outcome_tier_id, crit.pk)
