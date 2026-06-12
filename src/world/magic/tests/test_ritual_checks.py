"""Tests for world.magic.services.ritual_checks (#709)."""

from __future__ import annotations

from django.test import TestCase

from world.magic.exceptions import RitualCheckConfigMissing
from world.magic.services.ritual_checks import OutcomeTier, outcome_tier, perform_ritual_check


class OutcomeTierBoundaryTests(TestCase):
    """outcome_tier boundary cases over the canonical −10..+10 scale."""

    def test_10_is_crit(self):
        self.assertIs(outcome_tier(10), OutcomeTier.CRIT)

    def test_2_is_crit(self):
        self.assertIs(outcome_tier(2), OutcomeTier.CRIT)

    def test_1_is_success(self):
        self.assertIs(outcome_tier(1), OutcomeTier.SUCCESS)

    def test_0_is_fail(self):
        self.assertIs(outcome_tier(0), OutcomeTier.FAIL)

    def test_neg1_is_fail(self):
        self.assertIs(outcome_tier(-1), OutcomeTier.FAIL)

    def test_neg2_is_botch(self):
        self.assertIs(outcome_tier(-2), OutcomeTier.BOTCH)

    def test_neg10_is_botch(self):
        self.assertIs(outcome_tier(-10), OutcomeTier.BOTCH)


class PerformRitualCheckMissingConfigTests(TestCase):
    """perform_ritual_check raises RitualCheckConfigMissing when no config seeded."""

    def test_service_ritual_without_config_raises(self):
        from world.magic.constants import RitualExecutionKind
        from world.magic.factories import RitualFactory
        from world.scenes.factories import PersonaFactory

        ritual = RitualFactory(execution_kind=RitualExecutionKind.SERVICE)
        persona = PersonaFactory()
        character = persona.character_sheet.character

        with self.assertRaises(RitualCheckConfigMissing):
            perform_ritual_check(ritual.name, character)
