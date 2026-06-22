"""Tests for action prerequisite classes."""

from django.test import TestCase

from actions.prerequisites import PendingRitualEffectPrerequisite
from world.magic.constants import RitualExecutionKind
from world.magic.factories import CharacterResonanceFactory, RitualFactory
from world.magic.models import PendingRitualEffect


class PendingRitualEffectPrerequisiteTests(TestCase):
    def setUp(self):
        self.cr = CharacterResonanceFactory()
        self.sheet = self.cr.character_sheet
        self.character = self.sheet.character
        self.ritual = RitualFactory(
            name="Rite of Weaving",
            execution_kind=RitualExecutionKind.CEREMONY,
            service_function_path="",
        )
        self.prereq = PendingRitualEffectPrerequisite("Rite of Weaving")

    def test_not_met_without_pending_effect(self):
        met, msg = self.prereq.is_met(self.character)
        self.assertFalse(met)
        self.assertIn("Rite of Weaving", msg)

    def test_met_when_pending_effect_exists(self):
        PendingRitualEffect.objects.create(character=self.sheet, ritual=self.ritual)
        met, msg = self.prereq.is_met(self.character)
        self.assertTrue(met)
        self.assertEqual(msg, "")

    def test_not_met_when_ritual_missing(self):
        prereq = PendingRitualEffectPrerequisite("Nonexistent Ritual")
        met, msg = prereq.is_met(self.character)
        self.assertFalse(met)
        self.assertIn("Nonexistent Ritual", msg)
