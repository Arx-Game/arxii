from django.test import TestCase

from world.magic.constants import RegardPolarity
from world.magic.factories import ThreadPullEffectFactory


class RegardPolarityFieldTests(TestCase):
    def test_default_is_neutral(self):
        eff = ThreadPullEffectFactory()
        self.assertEqual(eff.regard_polarity, RegardPolarity.NEUTRAL)

    def test_choices_present(self):
        self.assertEqual(
            {c[0] for c in RegardPolarity.choices},
            {"offensive", "protective", "neutral"},
        )
