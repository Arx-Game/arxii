"""Tests for the generic consequence resolution pipeline."""

from unittest.mock import patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from actions.services import get_effective_consequences
from actions.types import WeightedConsequence
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.consequence_resolution import (
    apply_pool_deterministically,
    apply_pool_for_tier,
    select_consequence_from_result,
)
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import CheckTypeFactory, ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import CheckResult, PendingResolution, ResolutionContext
from world.conditions.factories import ConditionTemplateFactory
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.distinctions.types import DistinctionOrigin
from world.traits.factories import CheckOutcomeFactory


class ResolutionContextTests(TestCase):
    """Tests for ResolutionContext properties."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.location = ObjectDBFactory(db_key="ContextRoom")
        cls.character = ObjectDBFactory(db_key="ContextChar")
        ObjectDB.objects.filter(pk=cls.character.pk).update(db_location=cls.location)
        ObjectDB.flush_cached_instance(cls.character)
        cls.character = ObjectDB.objects.get(pk=cls.character.pk)

    def test_location_derived_from_character(self) -> None:
        """location property returns character.location."""
        context = ResolutionContext(character=self.character)
        assert context.location == self.location

    def test_display_label_from_challenge_instance(self) -> None:
        """display_label reads challenge template name."""
        from world.mechanics.factories import ChallengeTemplateFactory
        from world.mechanics.models import ChallengeInstance

        template = ChallengeTemplateFactory(name="Locked Door")
        instance = ChallengeInstance.objects.create(
            template=template,
            location=self.location,
            target_object=self.location,
            is_active=True,
            is_revealed=True,
        )
        context = ResolutionContext(character=self.character, challenge_instance=instance)
        assert context.display_label == "Locked Door"

    def test_display_label_raises_when_no_source(self) -> None:
        """display_label raises ValueError when no source is populated."""
        context = ResolutionContext(character=self.character)
        with self.assertRaises(ValueError):
            context.display_label  # noqa: B018


class SelectConsequenceTests(TestCase):
    """Tests for select_consequence()."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDBFactory(db_key="GenericResolveChar")
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
        cls.character = ObjectDBFactory(db_key="ApplyChar")
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


class GrantDistinctionResolutionTests(TestCase):
    """GRANT_DISTINCTION fires through apply_resolution() (select_consequence/apply_resolution
    path) and apply_pool_deterministically() (deterministic pool path) exactly like
    ADD_PROPERTY (#2037 acceptance criteria)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory(db_key="GrantDistResolutionChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.outcome = CheckOutcomeFactory(name="GrantDistSuccess", success_level=1)

    def _make_context(self) -> ResolutionContext:
        return ResolutionContext(character=self.character)

    def test_apply_resolution_grants_the_distinction(self) -> None:
        from world.checks.consequence_resolution import apply_resolution

        distinction = DistinctionFactory(name="Silver Tongue_resolution")
        consequence = ConsequenceFactory(
            outcome_tier=self.outcome, label="Grant dist via apply_resolution"
        )
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.GRANT_DISTINCTION,
            target=EffectTarget.SELF,
            distinction=distinction,
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
            selected_consequence=consequence,
        )

        results = apply_resolution(pending, self._make_context())

        assert len(results) == 1
        assert results[0].applied is True
        cd = CharacterDistinction.objects.get(character=self.sheet, distinction=distinction)
        assert cd.rank == 1
        assert cd.origin == DistinctionOrigin.CONSEQUENCE_POOL

    def test_apply_pool_deterministically_grants_the_distinction(self) -> None:
        distinction = DistinctionFactory(name="Silver Tongue_pool")
        consequence = ConsequenceFactory(label="Grant dist via pool")
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.GRANT_DISTINCTION,
            target=EffectTarget.SELF,
            distinction=distinction,
        )
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)

        applied = apply_pool_deterministically(pool=pool, context=self._make_context())

        assert len(applied) == 1
        assert applied[0].applied is True
        cd = CharacterDistinction.objects.get(character=self.sheet, distinction=distinction)
        assert cd.rank == 1


class SelectConsequenceFromResultTests(TestCase):
    """Test consequence selection using an existing check result."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.check_type = CheckTypeFactory()
        cls.outcome_success = CheckOutcomeFactory(name="Success", success_level=1)
        cls.outcome_failure = CheckOutcomeFactory(name="Failure", success_level=0)
        cls.consequence_a = ConsequenceFactory(
            outcome_tier=cls.outcome_success, label="Good A", weight=10
        )
        cls.consequence_b = ConsequenceFactory(
            outcome_tier=cls.outcome_success, label="Good B", weight=90
        )
        cls.consequence_fail = ConsequenceFactory(
            outcome_tier=cls.outcome_failure, label="Bad", weight=1
        )

    def _make_check_result(self, outcome: object) -> CheckResult:
        """Helper to build a CheckResult with minimal fields."""
        return CheckResult(
            check_type=self.check_type,
            outcome=outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

    def test_selects_from_matching_tier(self) -> None:
        check_result = self._make_check_result(self.outcome_success)
        weighted = [
            WeightedConsequence(consequence=self.consequence_a, weight=10, character_loss=False),
            WeightedConsequence(consequence=self.consequence_b, weight=90, character_loss=False),
            WeightedConsequence(consequence=self.consequence_fail, weight=1, character_loss=False),
        ]
        character = ObjectDBFactory(db_key="Tester")
        result = select_consequence_from_result(character, check_result, weighted)
        assert result.check_result == check_result
        # Selected consequence should be from success tier
        assert result.selected_consequence.outcome_tier == self.outcome_success

    def test_empty_list_returns_fallback(self) -> None:
        check_result = self._make_check_result(self.outcome_success)
        character = ObjectDBFactory(db_key="Tester")
        result = select_consequence_from_result(character, check_result, [])
        assert result.selected_consequence.pk is None  # Synthetic fallback

    def test_no_matching_tier_returns_fallback(self) -> None:
        check_result = self._make_check_result(self.outcome_failure)
        # Only success-tier consequences in the list
        weighted = [
            WeightedConsequence(consequence=self.consequence_a, weight=10, character_loss=False),
        ]
        character = ObjectDBFactory(db_key="Tester")
        result = select_consequence_from_result(character, check_result, weighted)
        assert result.selected_consequence.pk is None  # Synthetic fallback

    def test_integrates_with_pool_inheritance(self) -> None:
        """Test that get_effective_consequences output works with select_consequence_from_result."""
        pool = ConsequencePoolFactory(name="Integration Pool")
        ConsequencePoolEntryFactory(pool=pool, consequence=self.consequence_a)
        ConsequencePoolEntryFactory(pool=pool, consequence=self.consequence_fail)

        effective = get_effective_consequences(pool)
        check_result = self._make_check_result(self.outcome_success)
        character = ObjectDBFactory(db_key="Integrator")
        result = select_consequence_from_result(character, check_result, effective)
        assert result.selected_consequence.outcome_tier == self.outcome_success


class ApplyPoolForTierTests(TestCase):
    """apply_pool_for_tier fires only Consequence rows matching the given tier.

    Uses APPLY_CONDITION (the same proven-safe, zero-location-dependency effect
    type SelectConsequenceTests already uses in this file) so a fired effect is
    observable via its description, distinguishing "filtered correctly" from
    "no-op regardless of filtering."
    """

    def test_fires_only_matching_tier_consequences(self) -> None:
        """Only consequences matching the provided tier are applied."""
        character = ObjectDBFactory(db_key="TierPoolTestChar")
        decisive = CheckOutcomeFactory(name="Decisive Victory", success_level=6)
        marginal = CheckOutcomeFactory(name="Marginal Victory", success_level=1)

        matching = ConsequenceFactory(outcome_tier=decisive)
        non_matching = ConsequenceFactory(outcome_tier=marginal)
        matching_condition = ConditionTemplateFactory(name="Emboldened_tier_match")
        non_matching_condition = ConditionTemplateFactory(name="Emboldened_tier_nomatch")
        ConsequenceEffectFactory(
            consequence=matching,
            effect_type=EffectType.APPLY_CONDITION,
            target=EffectTarget.SELF,
            condition_template=matching_condition,
            condition_severity=1,
        )
        ConsequenceEffectFactory(
            consequence=non_matching,
            effect_type=EffectType.APPLY_CONDITION,
            target=EffectTarget.SELF,
            condition_template=non_matching_condition,
            condition_severity=1,
        )
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=matching)
        ConsequencePoolEntryFactory(pool=pool, consequence=non_matching)

        context = ResolutionContext(character=character, outcome_tier=decisive)
        applied = apply_pool_for_tier(pool=pool, outcome_tier=decisive, context=context)

        assert len(applied) == 1
        assert "Emboldened_tier_match" in applied[0].description
        assert "Emboldened_tier_nomatch" not in applied[0].description

    def test_fires_nothing_when_no_tier_matches(self) -> None:
        """No consequences are applied when the pool contains no matching tier."""
        character = ObjectDBFactory(db_key="TierPoolTestChar2")
        decisive = CheckOutcomeFactory(name="Decisive Victory 2", success_level=6)
        marginal = CheckOutcomeFactory(name="Marginal Victory 2", success_level=1)

        non_matching = ConsequenceFactory(outcome_tier=marginal)
        condition = ConditionTemplateFactory(name="Emboldened_no_match")
        ConsequenceEffectFactory(
            consequence=non_matching,
            effect_type=EffectType.APPLY_CONDITION,
            target=EffectTarget.SELF,
            condition_template=condition,
            condition_severity=1,
        )
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=non_matching)

        context = ResolutionContext(character=character, outcome_tier=decisive)
        applied = apply_pool_for_tier(pool=pool, outcome_tier=decisive, context=context)
        assert applied == []
