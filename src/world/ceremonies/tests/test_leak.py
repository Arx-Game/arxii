"""Twisted-rite leak clue (#2289, #4331): a sensed hunch is a lead, not a reveal."""

from __future__ import annotations

from django.test import TestCase

from world.ceremonies.leak import _observer_senses_twist
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.clues.constants import ClueResolution
from world.clues.models import CharacterClue
from world.roster.factories import RosterEntryFactory
from world.secrets.factories import SecretFactory
from world.secrets.models import SecretKnowledge
from world.traits.factories import CheckOutcomeFactory


class TwistedRiteLeakTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.observer_entry = RosterEntryFactory()
        cls.officiant_entry = RosterEntryFactory()
        cls.secret = SecretFactory()
        cls.check_type = CheckTypeFactory(name="Leak Search")
        cls.success = CheckOutcomeFactory(name="Leak Success", success_level=1)

    def test_witness_holds_a_research_lead_and_does_not_learn_the_secret(self) -> None:
        sheet = self.observer_entry.character_sheet
        with force_check_outcome(self.success):
            sensed = _observer_senses_twist(
                observer=sheet.character,
                observer_sheet=sheet,
                officiant_sheet=self.officiant_entry.character_sheet,
                check_type=self.check_type,
                difficulty=1,
                worship_secret=self.secret,
            )

        self.assertTrue(sensed)
        held = CharacterClue.objects.get(roster_entry=self.observer_entry)
        self.assertEqual(held.clue.resolution_mode, ClueResolution.RESEARCH)
        self.assertFalse(SecretKnowledge.objects.filter(secret=self.secret).exists())
