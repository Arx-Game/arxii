"""Tests for ResolutionContext's outcome_tier field."""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.checks.types import ResolutionContext
from world.traits.factories import CheckOutcomeFactory


class ResolutionContextOutcomeTierTests(TestCase):
    """Test ResolutionContext.outcome_tier field."""

    def test_outcome_tier_defaults_to_none(self) -> None:
        """outcome_tier should default to None."""
        character = ObjectDBFactory(db_key="ResolutionContextTestChar")
        context = ResolutionContext(character=character)
        assert context.outcome_tier is None

    def test_outcome_tier_can_be_set(self) -> None:
        """outcome_tier should be settable on initialization."""
        character = ObjectDBFactory(db_key="ResolutionContextTestChar2")
        tier = CheckOutcomeFactory(name="Overwhelming Victory", success_level=9)
        context = ResolutionContext(character=character, outcome_tier=tier)
        assert context.outcome_tier == tier
