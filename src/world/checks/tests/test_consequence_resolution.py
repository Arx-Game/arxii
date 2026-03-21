"""Tests for the generic consequence resolution pipeline."""

from unittest.mock import patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import CheckResult, PendingResolution, ResolutionContext
from world.conditions.factories import ConditionTemplateFactory
from world.traits.factories import CheckOutcomeFactory


class SelectConsequenceTests(TestCase):
    """Tests for select_consequence()."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="GenericResolveChar")
        cls.outcome_success = CheckOutcomeFactory(name="GenSuccess", success_level=1)
        cls.outcome_failure = CheckOutcomeFactory(name="GenFailure", success_level=-1)

        cls.success_consequence = ConsequenceFactory(
            outcome_tier=cls.outcome_success,
            label="Generic success",
            weight=1,
        )
        cls.failure_consequence = ConsequenceFactory(
            outcome_tier=cls.outcome_failure,
            label="Generic failure",
            weight=1,
        )

    @patch("world.checks.consequence_resolution.perform_check")
    def test_selects_consequence_matching_outcome_tier(self, mock_check) -> None:
        """Selects a consequence that matches the check outcome tier."""
        from world.checks.consequence_resolution import select_consequence

        mock_check.return_value = CheckResult(
            check_type=None,
            outcome=self.outcome_success,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        consequences = [self.success_consequence, self.failure_consequence]
        result = select_consequence(
            character=self.character,
            check_type=None,
            target_difficulty=0,
            consequences=consequences,
        )
        assert isinstance(result, PendingResolution)
        assert result.selected_consequence.label == "Generic success"

    @patch("world.checks.consequence_resolution.perform_check")
    def test_returns_fallback_when_no_tier_matches(self, mock_check) -> None:
        """Creates an unsaved fallback consequence when no tier matches."""
        from world.checks.consequence_resolution import select_consequence

        unmatched_outcome = CheckOutcomeFactory(name="CritSuccess_gen", success_level=2)
        mock_check.return_value = CheckResult(
            check_type=None,
            outcome=unmatched_outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        consequences = [self.success_consequence, self.failure_consequence]
        result = select_consequence(
            character=self.character,
            check_type=None,
            target_difficulty=0,
            consequences=consequences,
        )
        assert result.selected_consequence.pk is None
        assert result.selected_consequence.label == "CritSuccess_gen"

    @patch("world.checks.consequence_resolution.perform_check")
    @patch("world.checks.services.get_rollmod", return_value=5)
    def test_character_loss_filtered_when_rollmod_positive(
        self,
        mock_rollmod: object,  # noqa: ARG002
        mock_check: object,
    ) -> None:
        """Character loss consequence is filtered out when character has positive rollmod."""
        from world.checks.consequence_resolution import select_consequence

        loss_consequence = ConsequenceFactory(
            outcome_tier=self.outcome_success,
            label="Character dies",
            weight=10000,
            character_loss=True,
        )
        safe_consequence = ConsequenceFactory(
            outcome_tier=self.outcome_success,
            label="Barely survives",
            weight=1,
            character_loss=False,
        )

        mock_check.return_value = CheckResult(
            check_type=None,
            outcome=self.outcome_success,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        consequences = [loss_consequence, safe_consequence]
        result = select_consequence(
            character=self.character,
            check_type=None,
            target_difficulty=0,
            consequences=consequences,
        )
        assert result.selected_consequence.character_loss is False

    @patch("world.checks.consequence_resolution.perform_check")
    def test_empty_pool_returns_fallback(self, mock_check) -> None:
        """Empty consequence pool returns unsaved fallback."""
        from world.checks.consequence_resolution import select_consequence

        mock_check.return_value = CheckResult(
            check_type=None,
            outcome=self.outcome_success,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        result = select_consequence(
            character=self.character,
            check_type=None,
            target_difficulty=0,
            consequences=[],
        )
        assert result.selected_consequence.pk is None


class ApplyResolutionTests(TestCase):
    """Tests for apply_resolution()."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="ApplyChar")
        cls.outcome = CheckOutcomeFactory(name="ApplySuccess", success_level=1)
        cls.consequence = ConsequenceFactory(
            outcome_tier=cls.outcome,
            label="Apply test consequence",
        )

    def _make_context(self) -> ResolutionContext:
        return ResolutionContext(
            character=self.character,
            challenge_instance=None,
            action_context=None,
        )

    def test_applies_effects_from_consequence(self) -> None:
        """apply_resolution() dispatches effects through handlers."""
        from world.checks.consequence_resolution import apply_resolution

        condition = ConditionTemplateFactory(name="Poisoned_apply")
        ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.APPLY_CONDITION,
            target=EffectTarget.SELF,
            condition_template=condition,
            condition_severity=2,
        )

        pending = PendingResolution(
            check_result=CheckResult(
                check_type=None,
                outcome=self.outcome,
                chart=None,
                roller_rank=None,
                target_rank=None,
                rank_difference=0,
                trait_points=0,
                aspect_bonus=0,
                total_points=0,
            ),
            selected_consequence=self.consequence,
        )
        context = self._make_context()
        results = apply_resolution(pending, context)

        assert len(results) == 1
        assert results[0].applied is True
        assert "Poisoned_apply" in results[0].description

    def test_unsaved_consequence_returns_empty(self) -> None:
        """Unsaved (fallback) consequence returns no effects."""
        from world.checks.consequence_resolution import apply_resolution

        fallback = ConsequenceFactory.build(
            outcome_tier=self.outcome,
            label="Fallback",
        )
        assert fallback.pk is None

        pending = PendingResolution(
            check_result=CheckResult(
                check_type=None,
                outcome=self.outcome,
                chart=None,
                roller_rank=None,
                target_rank=None,
                rank_difference=0,
                trait_points=0,
                aspect_bonus=0,
                total_points=0,
            ),
            selected_consequence=fallback,
        )
        context = self._make_context()
        results = apply_resolution(pending, context)
        assert results == []
