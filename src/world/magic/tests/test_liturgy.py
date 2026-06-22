"""Tests for RitualLiturgy model and RitualOfTheDuranceFactory."""

from django.test import TestCase

from world.magic.constants import ParticipationRule, RitualExecutionKind
from world.magic.factories import RitualOfTheDuranceFactory


class RitualOfTheDuranceFactoryTests(TestCase):
    """Tests for the Durance ritual factory and its linked RitualLiturgy."""

    @classmethod
    def setUpTestData(cls):
        cls.ritual = RitualOfTheDuranceFactory()

    def test_ritual_execution_kind_is_service(self):
        """Durance ritual dispatches via a service function."""
        self.assertEqual(self.ritual.execution_kind, RitualExecutionKind.SERVICE)

    def test_ritual_participation_rule_is_induction(self):
        """Durance ritual uses the INDUCTION participation rule."""
        self.assertEqual(self.ritual.participation_rule, ParticipationRule.INDUCTION)

    def test_ritual_min_participants(self):
        """Durance ritual requires at least 2 participants (officiant + inductee)."""
        self.assertEqual(self.ritual.min_participants, 2)

    def test_ritual_service_function_path(self):
        """Service path string must exactly match the Task 4 target (not resolved yet)."""
        self.assertEqual(
            self.ritual.service_function_path,
            "world.progression.services.advancement.advance_class_level_via_session",
        )

    def test_liturgy_exists(self):
        """RitualLiturgy is created alongside the Ritual."""
        self.assertTrue(hasattr(self.ritual, "liturgy"))
        self.assertIsNotNone(self.ritual.liturgy)

    def test_liturgy_opening_call_is_non_empty(self):
        """The authored opening call must be non-empty."""
        self.assertNotEqual(self.ritual.liturgy.opening_call, "")
        self.assertTrue(len(self.ritual.liturgy.opening_call) > 0)

    def test_ritual_full_clean_passes(self):
        """The SERVICE/INDUCTION row is valid against model constraints."""
        self.ritual.full_clean()
