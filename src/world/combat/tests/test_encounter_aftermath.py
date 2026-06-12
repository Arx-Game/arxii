"""Tests for encounter aftermath (#876): outcome fields, rules, completion seam."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.combat.constants import EncounterOutcome, RiskLevel
from world.combat.factories import (
    CombatEncounterFactory,
    EncounterAftermathRuleFactory,
)


class EncounterOutcomeFieldTests(TestCase):
    def test_encounter_outcome_defaults_empty(self) -> None:
        encounter = CombatEncounterFactory()
        self.assertEqual(encounter.outcome, "")
        self.assertIsNone(encounter.completed_at)


class EncounterAftermathRuleTests(TestCase):
    def test_unique_per_outcome_risk_cell(self) -> None:
        EncounterAftermathRuleFactory(outcome=EncounterOutcome.DEFEAT, risk_level=RiskLevel.LETHAL)
        with self.assertRaises(IntegrityError), transaction.atomic():
            EncounterAftermathRuleFactory(
                outcome=EncounterOutcome.DEFEAT, risk_level=RiskLevel.LETHAL
            )
