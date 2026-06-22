"""Tests for PerformRitualAction CEREMONY branch."""

from django.test import TestCase

from actions.definitions.ritual import PerformRitualAction
from world.magic.constants import RitualExecutionKind
from world.magic.factories import CharacterResonanceFactory, RitualFactory
from world.magic.models import PendingRitualEffect


class PerformRitualActionCeremonyTests(TestCase):
    def setUp(self):
        self.cr = CharacterResonanceFactory()
        self.sheet = self.cr.character_sheet
        self.character = self.sheet.character
        self.ritual = RitualFactory(
            name="Rite of Weaving",
            execution_kind=RitualExecutionKind.CEREMONY,
            service_function_path="",
        )

    def test_ceremony_creates_pending_effect(self):
        action = PerformRitualAction()
        result = action.run(self.character, ritual=self.ritual)
        self.assertTrue(result.success)
        self.assertIn("begin", result.message.lower())
        self.assertTrue(
            PendingRitualEffect.objects.filter(character=self.sheet, ritual=self.ritual).exists()
        )

    def test_ceremony_already_in_progress_fails(self):
        PendingRitualEffect.objects.create(character=self.sheet, ritual=self.ritual)
        action = PerformRitualAction()
        result = action.run(self.character, ritual=self.ritual)
        self.assertFalse(result.success)
        self.assertIn("already in progress", result.message)
