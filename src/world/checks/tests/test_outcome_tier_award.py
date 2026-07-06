"""Tests for the shared OutcomeTierAward abstract base (#1207)."""

from __future__ import annotations

from django.test import TestCase

from world.checks.models import OutcomeTierAward


class OutcomeTierAwardBaseTests(TestCase):
    def test_is_abstract(self):
        self.assertTrue(OutcomeTierAward._meta.abstract)

    def test_outcome_tier_is_one_to_one_to_check_outcome(self):
        field = OutcomeTierAward._meta.get_field("outcome_tier")
        self.assertTrue(field.one_to_one)
        # On an *abstract* model's own field, Django's lazy string-relation
        # resolution never fires (only a concrete subclass's cloned field gets
        # resolved when that subclass is prepared), so `related_model` here
        # stays the unresolved "app_label.ModelName" string rather than the
        # class itself. Accept either form so this test isn't coupled to that
        # resolution-timing detail.
        related = field.related_model
        related_name = related if isinstance(related, str) else related.__name__
        self.assertIn(related_name, ("traits.CheckOutcome", "CheckOutcome"))

    def test_ordering_is_by_success_level(self):
        self.assertEqual(OutcomeTierAward._meta.ordering, ["outcome_tier__success_level"])
