"""Tests for LegendHonor, the Rite of Honors paid-testimony ledger row (#3466)."""

from django.db import IntegrityError
from django.test import TestCase

from world.scenes.factories import PersonaFactory
from world.societies.factories import LegendEntryFactory, LegendHonorFactory


class LegendHonorTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.deed = LegendEntryFactory()
        cls.persona = PersonaFactory()
        cls.other_persona = PersonaFactory()

    def test_one_honor_per_persona_per_deed(self) -> None:
        LegendHonorFactory(deed=self.deed, honorer=self.persona)
        with self.assertRaises(IntegrityError):
            LegendHonorFactory(deed=self.deed, honorer=self.persona)

    def test_two_personas_may_both_honor(self) -> None:
        LegendHonorFactory(deed=self.deed, honorer=self.persona)
        LegendHonorFactory(deed=self.deed, honorer=self.other_persona)
        assert self.deed.honors.count() == 2

    def test_newest_first(self) -> None:
        old = LegendHonorFactory(deed=self.deed, honorer=self.persona)
        new = LegendHonorFactory(deed=self.deed, honorer=self.other_persona)
        assert list(self.deed.honors.all()) == [new, old]
