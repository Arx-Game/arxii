"""Tests for the ENCOUNTER_COMPLETED → beat auto-wiring (#1746)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.combat.beat_wiring import classify_battle_outcome
from world.combat.constants import EncounterOutcome, RiskLevel
from world.combat.factories import CombatEncounterFactory
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


class ClassifyBattleOutcomeTests(TestCase):
    """classify_battle_outcome: (EncounterOutcome, risk_level) → CheckOutcome | None."""

    def test_victory_returns_mapped_check_outcome(self) -> None:
        tier = CheckOutcome.objects.create(name="Decisive Victory", success_level=5)
        EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.VICTORY,
            risk_level=RiskLevel.LETHAL,
            check_outcome=tier,
        )
        encounter = CombatEncounterFactory(
            outcome=EncounterOutcome.VICTORY, risk_level=RiskLevel.LETHAL
        )
        self.assertEqual(classify_battle_outcome(encounter), tier)

    def test_unmapped_pair_returns_none(self) -> None:
        """A pair with no mapping row → None (signals PENDING_GM_REVIEW)."""
        encounter = CombatEncounterFactory(outcome=EncounterOutcome.FLED, risk_level=RiskLevel.LOW)
        self.assertIsNone(classify_battle_outcome(encounter))

    def test_null_check_outcome_mapping_returns_none(self) -> None:
        """A mapping row whose check_outcome is null → None (FLED/ABANDONED review)."""
        EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.ABANDONED,
            risk_level=RiskLevel.MODERATE,
            check_outcome=None,
        )
        encounter = CombatEncounterFactory(
            outcome=EncounterOutcome.ABANDONED, risk_level=RiskLevel.MODERATE
        )
        self.assertIsNone(classify_battle_outcome(encounter))

    def test_empty_outcome_raises_value_error(self) -> None:
        """An encounter with no outcome set is programmer error."""
        encounter = CombatEncounterFactory(outcome="")
        with self.assertRaises(ValueError):
            classify_battle_outcome(encounter)
