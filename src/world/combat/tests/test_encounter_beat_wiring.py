"""Tests for the ENCOUNTER_COMPLETED → beat auto-wiring (#1746)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.combat.constants import EncounterOutcome, RiskLevel
from world.combat.models import EncounterOutcomeMapping
from world.traits.models import CheckOutcome


class EncounterOutcomeMappingModelTests(TestCase):
    """Model-level tests for EncounterOutcomeMapping."""

    def test_mapping_unique_per_outcome_risk(self) -> None:
        """Each (outcome, risk_level) pair maps to exactly one CheckOutcome."""
        outcome = CheckOutcome.objects.create(name="Victory", success_level=5)
        EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.VICTORY,
            risk_level=RiskLevel.MODERATE,
            check_outcome=outcome,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EncounterOutcomeMapping.objects.create(
                    outcome=EncounterOutcome.VICTORY,
                    risk_level=RiskLevel.MODERATE,
                    check_outcome=outcome,
                )

    def test_mapping_allows_null_check_outcome(self) -> None:
        """A null check_outcome means 'resolve to PENDING_GM_REVIEW' (FLED/ABANDONED)."""
        mapping = EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.FLED,
            risk_level=RiskLevel.MODERATE,
            check_outcome=None,
        )
        self.assertIsNone(mapping.check_outcome)

    def test_str_representation(self) -> None:
        outcome = CheckOutcome.objects.create(name="Defeat", success_level=-5)
        mapping = EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.DEFEAT,
            risk_level=RiskLevel.LETHAL,
            check_outcome=outcome,
        )
        self.assertIn("defeat", str(mapping).lower())
        self.assertIn("lethal", str(mapping).lower())
