"""Tests for attempt system type definitions."""

from django.test import TestCase

from world.attempts.factories import AttemptConsequenceFactory, AttemptTemplateFactory
from world.attempts.types import AttemptResult, ConsequenceDisplay
from world.checks.factories import CheckTypeFactory
from world.traits.factories import CheckOutcomeFactory


class ConsequenceDisplayTests(TestCase):
    """Test ConsequenceDisplay dataclass."""

    def test_consequence_display_fields(self):
        display = ConsequenceDisplay(
            label="Guard raises alarm",
            tier_name="Catastrophic Failure",
            weight=3,
            is_selected=False,
        )
        assert display.label == "Guard raises alarm"
        assert display.tier_name == "Catastrophic Failure"
        assert display.weight == 3
        assert display.is_selected is False


class AttemptResultTests(TestCase):
    """Test AttemptResult dataclass."""

    @classmethod
    def setUpTestData(cls):
        cls.check_type = CheckTypeFactory(name="TypeTestCheck")
        cls.outcome = CheckOutcomeFactory(name="TypeTestOutcome", success_level=-1)
        cls.template = AttemptTemplateFactory(
            name="TypeTestTemplate",
            check_type=cls.check_type,
        )
        cls.consequence = AttemptConsequenceFactory(
            attempt_template=cls.template,
            outcome_tier=cls.outcome,
            label="Test consequence",
        )

    def test_attempt_result_fields(self):
        displays = [
            ConsequenceDisplay(
                label="Test consequence",
                tier_name="TypeTestOutcome",
                weight=1,
                is_selected=True,
            )
        ]
        result = AttemptResult(
            attempt_template=self.template,
            check_result=None,
            consequence=self.consequence,
            all_consequences=displays,
        )
        assert result.attempt_template == self.template
        assert result.consequence == self.consequence
        assert len(result.all_consequences) == 1
        assert result.all_consequences[0].is_selected is True
