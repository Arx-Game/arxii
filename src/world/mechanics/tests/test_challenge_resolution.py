"""Tests for challenge resolution service."""

from typing import cast
from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import ResolutionContext
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.mechanics.constants import CapabilitySourceType, ResolutionType
from world.mechanics.factories import (
    ApplicationFactory,
    ApproachConsequenceFactory,
    ChallengeApproachFactory,
    ChallengeTemplateConsequenceFactory,
    ChallengeTemplateFactory,
    ChallengeTemplatePropertyFactory,
    PropertyFactory,
)
from world.mechanics.models import ChallengeInstance, CharacterChallengeRecord, ObjectProperty
from world.mechanics.types import (
    CapabilitySource,
    ChallengeResolutionError,
    ChallengeResolutionResult,
)
from world.traits.factories import CheckOutcomeFactory


def _make_source(
    capability_name: str = "fire_control",
    capability_id: int = 1,
    value: int = 10,
) -> CapabilitySource:
    """Helper to build a CapabilitySource for tests."""
    return CapabilitySource(
        capability_name=capability_name,
        capability_id=capability_id,
        value=value,
        source_type=CapabilitySourceType.TECHNIQUE,
        source_name="Test Technique",
        source_id=1,
    )


class ResolveValidationTests(TestCase):
    """Tests for resolve_challenge() validation."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="ResolveChar")
        cls.location = ObjectDB.objects.create(db_key="ResolveRoom")

        cls.capability = CapabilityTypeFactory(name="fire_resolve")
        cls.prop = PropertyFactory(name="flammable_resolve")
        cls.application = ApplicationFactory(
            name="BurnResolve",
            capability=cls.capability,
            target_property=cls.prop,
        )
        cls.outcome = CheckOutcomeFactory(name="Success_resolve", success_level=1)

        cls.template = ChallengeTemplateFactory(
            name="Wooden Gate",
            severity=5,
        )
        ChallengeTemplatePropertyFactory(
            challenge_template=cls.template,
            property=cls.prop,
            value=5,
        )
        cls.consequence = ConsequenceFactory(
            outcome_tier=cls.outcome,
            label="Gate burns down",
        )
        ChallengeTemplateConsequenceFactory(
            challenge_template=cls.template,
            consequence=cls.consequence,
        )
        cls.approach = ChallengeApproachFactory(
            challenge_template=cls.template,
            application=cls.application,
            display_name="Burn the gate",
        )
        cls.challenge = ChallengeInstance.objects.create(
            template=cls.template,
            location=cls.location,
            is_active=True,
            is_revealed=True,
        )
        cls.source = _make_source(
            capability_name="fire_resolve",
            capability_id=cls.capability.id,
        )

    def test_inactive_challenge_raises(self) -> None:
        """Cannot resolve an inactive challenge."""
        from world.mechanics.challenge_resolution import resolve_challenge

        self.challenge.is_active = False
        self.challenge.save()
        try:
            with self.assertRaises(ChallengeResolutionError):
                resolve_challenge(self.character, self.challenge, self.approach, self.source)
        finally:
            self.challenge.is_active = True
            self.challenge.save()

    def test_unrevealed_challenge_raises(self) -> None:
        """Cannot resolve an unrevealed challenge."""
        from world.mechanics.challenge_resolution import resolve_challenge

        self.challenge.is_revealed = False
        self.challenge.save()
        try:
            with self.assertRaises(ChallengeResolutionError):
                resolve_challenge(self.character, self.challenge, self.approach, self.source)
        finally:
            self.challenge.is_revealed = True
            self.challenge.save()

    def test_already_resolved_raises(self) -> None:
        """Cannot resolve a challenge twice."""
        from world.mechanics.challenge_resolution import resolve_challenge

        CharacterChallengeRecord.objects.create(
            character=self.character,
            challenge_instance=self.challenge,
            approach=self.approach,
        )
        try:
            with self.assertRaises(ChallengeResolutionError):
                resolve_challenge(self.character, self.challenge, self.approach, self.source)
        finally:
            CharacterChallengeRecord.objects.filter(
                character=self.character,
                challenge_instance=self.challenge,
            ).delete()

    def test_wrong_approach_raises(self) -> None:
        """Cannot use an approach from a different template."""
        from world.mechanics.challenge_resolution import resolve_challenge

        other_template = ChallengeTemplateFactory(name="Other Challenge")
        other_approach = ChallengeApproachFactory(
            challenge_template=other_template,
            application=self.application,
        )
        with self.assertRaises(ChallengeResolutionError):
            resolve_challenge(self.character, self.challenge, other_approach, self.source)


class ConsequenceSelectionTests(TestCase):
    """Tests for consequence selection logic."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = ChallengeTemplateFactory(name="SelectionChallenge")
        cls.outcome_success = CheckOutcomeFactory(name="Success_sel", success_level=1)
        cls.outcome_failure = CheckOutcomeFactory(name="Failure_sel", success_level=-1)

        cls.capability = CapabilityTypeFactory(name="select_cap")
        cls.prop = PropertyFactory(name="select_prop")
        cls.application = ApplicationFactory(
            name="SelectApp",
            capability=cls.capability,
            target_property=cls.prop,
        )
        cls.approach = ChallengeApproachFactory(
            challenge_template=cls.template,
            application=cls.application,
        )

        # Template-level consequences (via through model)
        cls.success_consequence = ConsequenceFactory(
            outcome_tier=cls.outcome_success,
            label="Template success",
            weight=1,
        )
        ChallengeTemplateConsequenceFactory(
            challenge_template=cls.template,
            consequence=cls.success_consequence,
        )
        cls.failure_consequence = ConsequenceFactory(
            outcome_tier=cls.outcome_failure,
            label="Template failure",
            weight=1,
        )
        ChallengeTemplateConsequenceFactory(
            challenge_template=cls.template,
            consequence=cls.failure_consequence,
        )

    def test_selects_matching_tier(self) -> None:
        """Selects consequence matching the outcome tier."""
        from world.mechanics.challenge_resolution import _select_consequence

        consequence, _ = _select_consequence(
            self.approach,
            self.template,
            self.outcome_success,
            ObjectDB.objects.create(db_key="SelChar1"),
        )
        assert consequence.label == "Template success"

    def test_approach_consequence_overrides_template(self) -> None:
        """Approach-level consequence overrides template-level for same tier."""
        from world.mechanics.challenge_resolution import _select_consequence

        override = ConsequenceFactory(
            outcome_tier=self.outcome_success,
            label="Approach success override",
            weight=1,
        )
        ApproachConsequenceFactory(
            approach=self.approach,
            consequence=override,
        )
        consequence, _ = _select_consequence(
            self.approach,
            self.template,
            self.outcome_success,
            ObjectDB.objects.create(db_key="SelChar2"),
        )
        assert consequence.label == "Approach success override"

    def test_fallback_when_no_consequences(self) -> None:
        """Creates fallback consequence when no tier matches."""
        from world.mechanics.challenge_resolution import _select_consequence

        other_outcome = CheckOutcomeFactory(name="CritSuccess_sel", success_level=2)
        consequence, _ = _select_consequence(
            self.approach,
            self.template,
            other_outcome,
            ObjectDB.objects.create(db_key="SelChar3"),
        )
        assert consequence.label == "CritSuccess_sel"
        assert consequence.pk is None  # Unsaved fallback


class EffectHandlerTests(TestCase):
    """Tests for consequence effect handlers."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.location = ObjectDB.objects.create(db_key="EffectRoom")
        cls.character = ObjectDB.objects.create(db_key="EffectChar")
        # Set location via FK update to avoid Evennia's at_db_location_postsave hook.
        # Flush the SharedMemoryModel identity-map cache so the next get() hits the DB.
        ObjectDB.objects.filter(pk=cls.character.pk).update(db_location=cls.location)
        ObjectDB.flush_cached_instance(cls.character)
        cls.character = ObjectDB.objects.get(pk=cls.character.pk)
        cls.template = ChallengeTemplateFactory(name="EffectChallenge")
        cls.outcome = CheckOutcomeFactory(name="Success_eff", success_level=1)
        cls.consequence = ConsequenceFactory(
            outcome_tier=cls.outcome,
            label="Effect test",
        )
        ChallengeTemplateConsequenceFactory(
            challenge_template=cls.template,
            consequence=cls.consequence,
        )
        cls.challenge = ChallengeInstance.objects.create(
            template=cls.template,
            location=cls.location,
            is_active=True,
            is_revealed=True,
        )

    def test_apply_condition_effect(self) -> None:
        """APPLY_CONDITION calls apply_condition on the character."""
        from world.mechanics.effect_handlers import apply_effect

        condition = ConditionTemplateFactory(name="Burning_eff")
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.APPLY_CONDITION,
            target=EffectTarget.SELF,
            condition_template=condition,
            condition_severity=3,
        )
        context = ResolutionContext(character=self.character, challenge_instance=self.challenge)
        result = apply_effect(effect, context)
        assert result.applied is True
        assert "Burning_eff" in result.description

    def test_add_property_effect(self) -> None:
        """ADD_PROPERTY creates an ObjectProperty on the location."""
        from world.mechanics.effect_handlers import apply_effect

        prop = PropertyFactory(name="flooded_eff")
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.ADD_PROPERTY,
            target=EffectTarget.LOCATION,
            property=prop,
            property_value=5,
        )
        context = ResolutionContext(character=self.character, challenge_instance=self.challenge)
        result = apply_effect(effect, context)
        assert result.applied is True
        assert result.created_instance is not None
        assert result.created_instance.property == prop
        assert ObjectProperty.objects.filter(
            object=self.location,
            property=prop,
            value=5,
        ).exists()

    def test_remove_property_effect(self) -> None:
        """REMOVE_PROPERTY deletes the ObjectProperty from location."""
        from world.mechanics.effect_handlers import apply_effect

        prop = PropertyFactory(name="blocked_eff")
        ObjectProperty.objects.create(
            object=self.location,
            property=prop,
            value=3,
        )
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.REMOVE_PROPERTY,
            target=EffectTarget.LOCATION,
            property=prop,
        )
        context = ResolutionContext(character=self.character, challenge_instance=self.challenge)
        result = apply_effect(effect, context)
        assert result.applied is True
        assert not ObjectProperty.objects.filter(
            object=self.location,
            property=prop,
        ).exists()

    def test_remove_condition_effect(self) -> None:
        """REMOVE_CONDITION removes an active condition from the character."""
        from world.conditions.services import apply_condition
        from world.mechanics.effect_handlers import apply_effect

        condition = ConditionTemplateFactory(name="Cursed_eff")
        # First apply the condition so there's something to remove
        apply_condition(self.character, condition, severity=1)

        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.REMOVE_CONDITION,
            target=EffectTarget.SELF,
            condition_template=condition,
        )
        context = ResolutionContext(character=self.character, challenge_instance=self.challenge)
        result = apply_effect(effect, context)
        assert result.applied is True
        assert "Removed" in result.description

    def test_stubbed_effect_returns_not_applied(self) -> None:
        """Stubbed effect types return applied=False with reason."""
        from world.mechanics.effect_handlers import apply_effect

        damage_type = DamageTypeFactory(name="fire_eff")
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.DEAL_DAMAGE,
            damage_amount=10,
            damage_type=damage_type,
        )
        context = ResolutionContext(character=self.character, challenge_instance=self.challenge)
        result = apply_effect(effect, context)
        assert result.applied is False
        assert result.skip_reason != ""


class ResolveFullTests(TestCase):
    """Integration tests for the full resolve_challenge flow."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="FullResolveChar")
        cls.location = ObjectDB.objects.create(db_key="FullResolveRoom")

        cls.capability = CapabilityTypeFactory(name="fire_full")
        cls.prop = PropertyFactory(name="flammable_full")
        cls.application = ApplicationFactory(
            name="BurnFull",
            capability=cls.capability,
            target_property=cls.prop,
        )

        cls.outcome_success = CheckOutcomeFactory(name="Success_full", success_level=1)
        cls.outcome_failure = CheckOutcomeFactory(name="Failure_full", success_level=-1)

        cls.template = ChallengeTemplateFactory(
            name="Barricade",
            severity=5,
        )
        ChallengeTemplatePropertyFactory(
            challenge_template=cls.template,
            property=cls.prop,
            value=5,
        )

        cls.success_consequence = ConsequenceFactory(
            outcome_tier=cls.outcome_success,
            label="Barricade destroyed",
        )
        cls.success_link = ChallengeTemplateConsequenceFactory(
            challenge_template=cls.template,
            consequence=cls.success_consequence,
            resolution_type=ResolutionType.DESTROY,
        )
        cls.failure_consequence = ConsequenceFactory(
            outcome_tier=cls.outcome_failure,
            label="Barricade holds",
        )
        cls.failure_link = ChallengeTemplateConsequenceFactory(
            challenge_template=cls.template,
            consequence=cls.failure_consequence,
            resolution_type=ResolutionType.PERSONAL,
        )

        cls.approach = ChallengeApproachFactory(
            challenge_template=cls.template,
            application=cls.application,
            display_name="Burn the barricade",
        )

        cls.source = _make_source(
            capability_name="fire_full",
            capability_id=cls.capability.id,
        )

    def _make_challenge(self) -> ChallengeInstance:
        """Create a fresh challenge instance for each test."""
        return ChallengeInstance.objects.create(
            template=self.template,
            location=self.location,
            is_active=True,
            is_revealed=True,
        )

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_successful_resolution_destroys_challenge(self, mock_check) -> None:
        """Successful resolution with DESTROY consequence deactivates challenge."""
        from world.checks.types import CheckResult
        from world.mechanics.challenge_resolution import resolve_challenge

        mock_check.return_value = CheckResult(
            check_type=self.approach.check_type,
            outcome=self.outcome_success,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        challenge = self._make_challenge()
        result = resolve_challenge(self.character, challenge, self.approach, self.source)

        assert isinstance(result, ChallengeResolutionResult)
        assert result.consequence.label == "Barricade destroyed"
        assert result.challenge_deactivated is True
        assert result.resolution_type == ResolutionType.DESTROY

        challenge.refresh_from_db()
        assert challenge.is_active is False

        record = CharacterChallengeRecord.objects.get(
            character=self.character,
            challenge_instance=challenge,
        )
        assert record.outcome == self.outcome_success
        assert record.consequence == self.success_consequence

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_failed_resolution_personal(self, mock_check) -> None:
        """Failed resolution with PERSONAL consequence keeps challenge active."""
        from world.checks.types import CheckResult
        from world.mechanics.challenge_resolution import resolve_challenge

        mock_check.return_value = CheckResult(
            check_type=self.approach.check_type,
            outcome=self.outcome_failure,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        challenge = self._make_challenge()
        result = resolve_challenge(self.character, challenge, self.approach, self.source)

        assert result.consequence.label == "Barricade holds"
        assert result.challenge_deactivated is False
        assert result.resolution_type == ResolutionType.PERSONAL

        challenge.refresh_from_db()
        assert challenge.is_active is True

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_display_consequences_include_all_tiers(self, mock_check) -> None:
        """Display payload includes consequences from all tiers."""
        from world.checks.types import CheckResult
        from world.mechanics.challenge_resolution import resolve_challenge

        mock_check.return_value = CheckResult(
            check_type=self.approach.check_type,
            outcome=self.outcome_success,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        challenge = self._make_challenge()
        result = resolve_challenge(self.character, challenge, self.approach, self.source)

        labels = {d.label for d in result.display_consequences}
        assert "Barricade destroyed" in labels
        assert "Barricade holds" in labels

        selected = [d for d in result.display_consequences if d.is_selected]
        assert len(selected) == 1
        assert selected[0].label == "Barricade destroyed"

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_temporary_resolution_keeps_challenge_active(self, mock_check) -> None:
        """TEMPORARY resolution keeps challenge active (duration tracking is future work)."""
        from world.checks.types import CheckResult
        from world.mechanics.challenge_resolution import resolve_challenge

        # Create a TEMPORARY consequence
        temp_outcome = CheckOutcomeFactory(name="Success_temp", success_level=1)
        temp_consequence = ConsequenceFactory(
            outcome_tier=temp_outcome,
            label="Temporarily bypassed",
        )
        ChallengeTemplateConsequenceFactory(
            challenge_template=self.template,
            consequence=temp_consequence,
            resolution_type=ResolutionType.TEMPORARY,
            resolution_duration_rounds=3,
        )

        mock_check.return_value = CheckResult(
            check_type=self.approach.check_type,
            outcome=temp_outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        challenge = self._make_challenge()
        result = resolve_challenge(self.character, challenge, self.approach, self.source)

        assert result.resolution_type == ResolutionType.TEMPORARY
        assert result.challenge_deactivated is False

        challenge.refresh_from_db()
        assert challenge.is_active is True

    @patch("actions.services.apply_resolution", return_value=[])
    @patch("actions.services.select_consequence_from_result")
    @patch("actions.services.perform_check")
    def test_resolve_challenge_delegates_to_action_template(
        self,
        mock_check: object,
        mock_select: object,
        mock_apply: object,  # noqa: ARG002 — required positional param from @patch decorator order
    ) -> None:
        """When approach has action_template, resolution uses the template pipeline."""
        from actions.factories import (
            ActionTemplateFactory,
            ConsequencePoolEntryFactory,
            ConsequencePoolFactory,
        )
        from world.checks.types import CheckResult, PendingResolution
        from world.mechanics.challenge_resolution import resolve_challenge

        check_result = CheckResult(
            check_type=self.approach.check_type,
            outcome=self.outcome_success,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        cast(MagicMock, mock_check).return_value = check_result
        cast(MagicMock, mock_select).return_value = PendingResolution(
            check_result=check_result,
            selected_consequence=self.success_consequence,
        )

        pool = ConsequencePoolFactory(name="Template Pool")
        ConsequencePoolEntryFactory(pool=pool, consequence=self.success_consequence)
        template = ActionTemplateFactory(
            check_type=self.approach.check_type,
            consequence_pool=pool,
        )
        self.approach.action_template = template
        self.approach.save()

        try:
            challenge = self._make_challenge()
            result = resolve_challenge(self.character, challenge, self.approach, self.source)
            assert result.consequence is not None
            assert CharacterChallengeRecord.objects.filter(
                character=self.character,
                challenge_instance=challenge,
            ).exists()
        finally:
            self.approach.action_template = None
            self.approach.save()

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_approach_consequence_override_in_full_flow(self, mock_check) -> None:
        """Approach consequence override works through full resolution."""
        from world.checks.types import CheckResult
        from world.mechanics.challenge_resolution import resolve_challenge

        approach_outcome = CheckOutcomeFactory(name="Success_approach", success_level=1)

        # Template-level consequence
        template_consequence = ConsequenceFactory(
            outcome_tier=approach_outcome,
            label="Template version",
        )
        ChallengeTemplateConsequenceFactory(
            challenge_template=self.template,
            consequence=template_consequence,
            resolution_type=ResolutionType.DESTROY,
        )

        # Approach-level override
        override_consequence = ConsequenceFactory(
            outcome_tier=approach_outcome,
            label="Approach override version",
            weight=1,
        )
        ApproachConsequenceFactory(
            approach=self.approach,
            consequence=override_consequence,
        )

        mock_check.return_value = CheckResult(
            check_type=self.approach.check_type,
            outcome=approach_outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        challenge = self._make_challenge()
        result = resolve_challenge(self.character, challenge, self.approach, self.source)

        # Approach override was selected
        assert result.consequence.label == "Approach override version"
        # No effects applied (approach consequences don't carry effects)
        assert result.applied_effects == []
        # Record created with saved consequence
        record = CharacterChallengeRecord.objects.get(
            character=self.character,
            challenge_instance=challenge,
        )
        assert record.consequence == override_consequence
        assert record.outcome == approach_outcome
