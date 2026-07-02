"""Tests for Battle conclusion -> story beat auto-wiring (#1785)."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.battles.constants import BattleOutcome
from world.battles.models import BattleOutcomeMapping
from world.traits.models import CheckOutcome


class BattleOutcomeMappingModelTests(TestCase):
    """Model-level tests for BattleOutcomeMapping."""

    def test_mapping_unique_per_outcome(self) -> None:
        outcome = CheckOutcome.objects.create(name="Decisive Attacker Win", success_level=6)
        BattleOutcomeMapping.objects.create(
            outcome=BattleOutcome.ATTACKER_DECISIVE,
            check_outcome=outcome,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BattleOutcomeMapping.objects.create(
                    outcome=BattleOutcome.ATTACKER_DECISIVE,
                    check_outcome=outcome,
                )

    def test_mapping_allows_null_check_outcome(self) -> None:
        mapping = BattleOutcomeMapping.objects.create(
            outcome=BattleOutcome.DEFENDER_MARGINAL,
            check_outcome=None,
        )
        self.assertIsNone(mapping.check_outcome)

    def test_str_representation(self) -> None:
        outcome = CheckOutcome.objects.create(name="Decisive Defeat", success_level=-6)
        mapping = BattleOutcomeMapping.objects.create(
            outcome=BattleOutcome.DEFENDER_DECISIVE,
            check_outcome=outcome,
        )
        self.assertIn("Defender", str(mapping))
