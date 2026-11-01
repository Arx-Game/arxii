"""The one catalog match between a vow added effect and the techniques it rides (#4880).

``effect_rides_technique`` is the predicate the cast path and the static view use;
``techniques_ridden_by`` is its queryset form, which the vow page's rail counts.
Both read the row's function tag, then its gift or technique narrowing.
"""

from __future__ import annotations

from django.test import TestCase

from world.covenants.added_effects import effect_rides_technique, techniques_ridden_by
from world.covenants.factories import VowAddedEffectFactory
from world.magic.constants import TechniqueFunction
from world.magic.factories import GiftFactory, TechniqueFactory, TechniqueFunctionTagFactory


class EffectTechniqueMatchTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.storm = GiftFactory(name="Stormcalling")
        cls.tide = GiftFactory(name="Tidecalling")
        cls.bolt = TechniqueFactory(name="Bolt", gift=cls.storm)
        cls.squall = TechniqueFactory(name="Squall", gift=cls.storm)
        cls.wave = TechniqueFactory(name="Wave", gift=cls.tide)
        cls.ward = TechniqueFactory(name="Ward", gift=cls.storm)
        for technique in (cls.bolt, cls.squall, cls.wave):
            TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.BARRIER)
        TechniqueFunctionTagFactory(technique=cls.ward, function=TechniqueFunction.CLEANSE)

    def _functions(self, technique: object) -> set[str]:
        return {tag.function for tag in technique.function_tags.all()}

    def test_any_gift_rides_every_technique_with_the_function(self) -> None:
        effect = VowAddedEffectFactory(function=TechniqueFunction.BARRIER)
        self.assertEqual(list(techniques_ridden_by(effect)), [self.bolt, self.squall, self.wave])
        self.assertTrue(effect_rides_technique(effect, self.wave, self._functions(self.wave)))

    def test_gift_narrowing(self) -> None:
        effect = VowAddedEffectFactory(function=TechniqueFunction.BARRIER, gift=self.storm)
        self.assertEqual(list(techniques_ridden_by(effect)), [self.bolt, self.squall])
        self.assertTrue(effect_rides_technique(effect, self.bolt, self._functions(self.bolt)))
        self.assertFalse(effect_rides_technique(effect, self.wave, self._functions(self.wave)))

    def test_technique_narrowing(self) -> None:
        effect = VowAddedEffectFactory(function=TechniqueFunction.BARRIER, technique=self.squall)
        self.assertEqual(list(techniques_ridden_by(effect)), [self.squall])
        self.assertTrue(effect_rides_technique(effect, self.squall, self._functions(self.squall)))
        self.assertFalse(effect_rides_technique(effect, self.bolt, self._functions(self.bolt)))

    def test_function_mismatch(self) -> None:
        effect = VowAddedEffectFactory(function=TechniqueFunction.BARRIER, gift=self.storm)
        self.assertNotIn(self.ward, techniques_ridden_by(effect))
        self.assertFalse(effect_rides_technique(effect, self.ward, self._functions(self.ward)))
