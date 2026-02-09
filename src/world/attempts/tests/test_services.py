"""Tests for attempt resolution service."""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.attempts.factories import (
    AttemptCategoryFactory,
    AttemptConsequenceFactory,
    AttemptTemplateFactory,
)
from world.attempts.services import resolve_attempt
from world.attempts.types import AttemptResult
from world.checks.factories import CheckTypeFactory
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitValue,
    CheckRank,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitCategory,
    TraitType,
)

PATCH_RANDINT = "world.checks.services.random.randint"
PATCH_ROLLMOD = "world.attempts.services.get_rollmod"
PATCH_SELECT = "world.attempts.services._select_weighted_consequence"


class ResolveAttemptTests(TestCase):
    """Test the resolve_attempt service function."""

    @classmethod
    def setUpTestData(cls):
        Trait.flush_instance_cache()
        setup = CheckSystemSetupFactory.create()
        cls.outcomes = setup["outcomes"]
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        for rank_val, min_pts, name in [
            (0, 0, "AttemptNone"),
            (1, 10, "AttemptNovice"),
            (2, 25, "AttemptCompetent"),
            (3, 50, "AttemptExpert"),
        ]:
            CheckRank.objects.get_or_create(
                rank=rank_val,
                defaults={"min_points": min_pts, "name": name},
            )
        cls.character = CharacterFactory()
        cls.strength, _ = Trait.objects.get_or_create(
            name="attempt_test_strength",
            defaults={"trait_type": TraitType.STAT, "category": TraitCategory.PHYSICAL},
        )
        cls.check_type = CheckTypeFactory(name="attempt_test_strike")
        from decimal import Decimal

        from world.checks.factories import CheckTypeTraitFactory

        CheckTypeTraitFactory(
            check_type=cls.check_type,
            trait=cls.strength,
            weight=Decimal("1.0"),
        )
        # Create attempt template with consequences across tiers
        cls.category = AttemptCategoryFactory(name="attempt_test_combat")
        cls.template = AttemptTemplateFactory(
            name="attempt_test_attack",
            category=cls.category,
            check_type=cls.check_type,
        )
        # Failure consequences
        cls.failure_consequence = AttemptConsequenceFactory(
            attempt_template=cls.template,
            outcome_tier=cls.outcomes["failure"],
            label="You miss badly",
            weight=3,
        )
        cls.failure_loss = AttemptConsequenceFactory(
            attempt_template=cls.template,
            outcome_tier=cls.outcomes["failure"],
            label="You are slain",
            weight=1,
            character_loss=True,
        )
        # Success consequence
        cls.success_consequence = AttemptConsequenceFactory(
            attempt_template=cls.template,
            outcome_tier=cls.outcomes["success"],
            label="You strike true",
            weight=3,
        )

    def setUp(self):
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        ResultChart.clear_cache()

    def test_resolve_attempt_returns_attempt_result(self):
        CharacterTraitValue.objects.create(
            character=self.character,
            trait=self.strength,
            value=30,
        )
        with patch(PATCH_RANDINT, return_value=50):
            result = resolve_attempt(
                self.character,
                self.template,
                target_difficulty=0,
            )
        assert isinstance(result, AttemptResult)
        assert result.attempt_template == self.template
        assert result.check_result is not None
        assert result.consequence is not None

    def test_consequence_matches_outcome_tier(self):
        CharacterTraitValue.objects.create(
            character=self.character,
            trait=self.strength,
            value=30,
        )
        with patch(PATCH_RANDINT, return_value=50):
            result = resolve_attempt(
                self.character,
                self.template,
                target_difficulty=0,
            )
        # The consequence should belong to the same outcome tier as the check result
        assert result.consequence.outcome_tier == result.check_result.outcome

    def test_all_consequences_included_in_display(self):
        CharacterTraitValue.objects.create(
            character=self.character,
            trait=self.strength,
            value=30,
        )
        with patch(PATCH_RANDINT, return_value=50):
            result = resolve_attempt(
                self.character,
                self.template,
                target_difficulty=0,
            )
        # All consequences from all tiers should be in the display list
        all_labels = {c.label for c in result.all_consequences}
        assert "You miss badly" in all_labels
        assert "You are slain" in all_labels
        assert "You strike true" in all_labels

    def test_exactly_one_consequence_selected(self):
        CharacterTraitValue.objects.create(
            character=self.character,
            trait=self.strength,
            value=30,
        )
        with patch(PATCH_RANDINT, return_value=50):
            result = resolve_attempt(
                self.character,
                self.template,
                target_difficulty=0,
            )
        selected = [c for c in result.all_consequences if c.is_selected]
        assert len(selected) == 1

    def test_display_hides_character_loss_flag(self):
        """ConsequenceDisplay should not expose character_loss information."""
        CharacterTraitValue.objects.create(
            character=self.character,
            trait=self.strength,
            value=30,
        )
        with patch(PATCH_RANDINT, return_value=50):
            result = resolve_attempt(
                self.character,
                self.template,
                target_difficulty=0,
            )
        for display in result.all_consequences:
            assert not hasattr(display, "character_loss")

    def test_no_consequences_for_tier_falls_back_to_outcome_name(self):
        """If no consequences defined for a tier, use the outcome name as label."""
        # Create a template with NO consequences for any tier
        empty_template = AttemptTemplateFactory(
            name="attempt_test_empty",
            category=self.category,
            check_type=self.check_type,
        )
        CharacterTraitValue.objects.create(
            character=self.character,
            trait=self.strength,
            value=30,
        )
        with patch(PATCH_RANDINT, return_value=10):
            result = resolve_attempt(
                self.character,
                empty_template,
                target_difficulty=0,
            )
        # Should still return a result with the outcome name as the consequence label
        assert result.consequence is not None


class CharacterLossFilteringTests(TestCase):
    """Test rollmod-based character_loss filtering."""

    @classmethod
    def setUpTestData(cls):
        Trait.flush_instance_cache()
        setup = CheckSystemSetupFactory.create()
        cls.outcomes = setup["outcomes"]
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        for rank_val, min_pts, name in [
            (0, 0, "FilterNone"),
            (1, 10, "FilterNovice"),
            (2, 25, "FilterCompetent"),
            (3, 50, "FilterExpert"),
        ]:
            CheckRank.objects.get_or_create(
                rank=rank_val,
                defaults={"min_points": min_pts, "name": name},
            )
        cls.character = CharacterFactory()
        cls.strength, _ = Trait.objects.get_or_create(
            name="filter_test_strength",
            defaults={"trait_type": TraitType.STAT, "category": TraitCategory.PHYSICAL},
        )
        cls.check_type = CheckTypeFactory(name="filter_test_strike")
        from decimal import Decimal

        from world.checks.factories import CheckTypeTraitFactory

        CheckTypeTraitFactory(
            check_type=cls.check_type,
            trait=cls.strength,
            weight=Decimal("1.0"),
        )
        cls.category = AttemptCategoryFactory(name="filter_test_combat")
        cls.template = AttemptTemplateFactory(
            name="filter_test_attack",
            category=cls.category,
            check_type=cls.check_type,
        )
        # Failure tier: one character_loss, one non-loss
        cls.loss_consequence = AttemptConsequenceFactory(
            attempt_template=cls.template,
            outcome_tier=cls.outcomes["failure"],
            label="Killed in action",
            weight=1,
            character_loss=True,
        )
        cls.safe_consequence = AttemptConsequenceFactory(
            attempt_template=cls.template,
            outcome_tier=cls.outcomes["failure"],
            label="Badly wounded",
            weight=3,
        )

    def setUp(self):
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        ResultChart.clear_cache()

    def test_positive_rollmod_filters_character_loss(self):
        """Character with positive rollmod should never get character_loss consequence."""
        CharacterTraitValue.objects.create(
            character=self.character,
            trait=self.strength,
            value=30,
        )
        with (
            patch(PATCH_RANDINT, return_value=10),
            patch(PATCH_ROLLMOD, return_value=5),
            patch(PATCH_SELECT, return_value=self.loss_consequence),
        ):
            result = resolve_attempt(
                self.character,
                self.template,
                target_difficulty=100,
            )
        # Should have been filtered to the non-loss alternative
        assert result.consequence.character_loss is False
        assert result.consequence.label == "Badly wounded"

    def test_zero_rollmod_allows_character_loss(self):
        """Character with zero rollmod can get character_loss consequences."""
        CharacterTraitValue.objects.create(
            character=self.character,
            trait=self.strength,
            value=30,
        )
        with (
            patch(PATCH_RANDINT, return_value=10),
            patch(PATCH_ROLLMOD, return_value=0),
            patch(PATCH_SELECT, return_value=self.loss_consequence),
        ):
            result = resolve_attempt(
                self.character,
                self.template,
                target_difficulty=100,
            )
        assert result.consequence.character_loss is True

    def test_negative_rollmod_allows_character_loss(self):
        """Character with negative rollmod can get character_loss consequences."""
        CharacterTraitValue.objects.create(
            character=self.character,
            trait=self.strength,
            value=30,
        )
        with (
            patch(PATCH_RANDINT, return_value=10),
            patch(PATCH_ROLLMOD, return_value=-3),
            patch(PATCH_SELECT, return_value=self.loss_consequence),
        ):
            result = resolve_attempt(
                self.character,
                self.template,
                target_difficulty=100,
            )
        assert result.consequence.character_loss is True

    def test_positive_rollmod_selects_worst_non_loss_alternative(self):
        """With multiple non-loss alternatives, picks worst (highest display_order)."""
        multi_template = AttemptTemplateFactory(
            name="filter_test_multi",
            category=self.category,
            check_type=self.check_type,
        )
        loss = AttemptConsequenceFactory(
            attempt_template=multi_template,
            outcome_tier=self.outcomes["failure"],
            label="Death",
            weight=1,
            character_loss=True,
        )
        AttemptConsequenceFactory(
            attempt_template=multi_template,
            outcome_tier=self.outcomes["failure"],
            label="Scratch",
            weight=3,
            display_order=0,
        )
        AttemptConsequenceFactory(
            attempt_template=multi_template,
            outcome_tier=self.outcomes["failure"],
            label="Broken bones",
            weight=1,
            display_order=10,
        )
        CharacterTraitValue.objects.create(
            character=self.character,
            trait=self.strength,
            value=30,
        )
        with (
            patch(PATCH_RANDINT, return_value=10),
            patch(PATCH_ROLLMOD, return_value=5),
            patch(PATCH_SELECT, return_value=loss),
        ):
            result = resolve_attempt(
                self.character,
                multi_template,
                target_difficulty=100,
            )
        # Should select the worst non-loss alternative (highest display_order)
        assert result.consequence.label == "Broken bones"
        assert result.consequence.character_loss is False

    def test_positive_rollmod_no_alternative_keeps_character_loss(self):
        """If character_loss is the ONLY option, it stands with positive rollmod."""
        lone_template = AttemptTemplateFactory(
            name="filter_test_lone",
            category=self.category,
            check_type=self.check_type,
        )
        lone_loss = AttemptConsequenceFactory(
            attempt_template=lone_template,
            outcome_tier=self.outcomes["failure"],
            label="Only option: death",
            weight=1,
            character_loss=True,
        )
        CharacterTraitValue.objects.create(
            character=self.character,
            trait=self.strength,
            value=30,
        )
        with (
            patch(PATCH_RANDINT, return_value=10),
            patch(PATCH_ROLLMOD, return_value=5),
            patch(PATCH_SELECT, return_value=lone_loss),
        ):
            result = resolve_attempt(
                self.character,
                lone_template,
                target_difficulty=100,
            )
        # No alternative exists, so character_loss stands
        assert result.consequence.character_loss is True
