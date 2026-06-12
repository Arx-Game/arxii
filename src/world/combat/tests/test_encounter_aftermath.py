"""Tests for encounter aftermath (#876): outcome fields, rules, completion seam."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.combat.constants import EncounterOutcome, RiskLevel
from world.combat.factories import (
    CombatEncounterFactory,
    EncounterAftermathRuleFactory,
)
from world.combat.interaction_services import render_encounter_outcome_narration


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


class RenderEncounterOutcomeNarrationTests(TestCase):
    def test_victory_names_victors_and_defeated(self) -> None:
        narration = render_encounter_outcome_narration(
            outcome=EncounterOutcome.VICTORY,
            active_labels=["Alaric", "Bryn"],
            fled_labels=[],
            defeated_opponent_labels=["Gravewight"],
        )
        self.assertIn("victory", narration.lower())
        self.assertIn("Alaric and Bryn", narration)
        self.assertIn("Gravewight", narration)

    def test_fled_outcome_names_the_scattered(self) -> None:
        narration = render_encounter_outcome_narration(
            outcome=EncounterOutcome.FLED,
            active_labels=[],
            fled_labels=["Alaric"],
            defeated_opponent_labels=[],
        )
        self.assertIn("Alaric", narration)
        self.assertIn("fled", narration.lower())

    def test_defeat_names_the_fallen(self) -> None:
        narration = render_encounter_outcome_narration(
            outcome=EncounterOutcome.DEFEAT,
            active_labels=["Alaric", "Bryn"],
            fled_labels=["Cael"],
            defeated_opponent_labels=[],
        )
        self.assertIn("Alaric and Bryn can fight no longer", narration)
        self.assertIn("Cael fled the field", narration)
