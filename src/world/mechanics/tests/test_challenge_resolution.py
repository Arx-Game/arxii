"""Tests for challenge resolution service."""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.mechanics.constants import CapabilitySourceType, EffectTarget, EffectType
from world.mechanics.factories import (
    ApplicationFactory,
    ApproachConsequenceFactory,
    ChallengeApproachFactory,
    ChallengeConsequenceFactory,
    ChallengeTemplateFactory,
    ChallengeTemplatePropertyFactory,
    ConsequenceEffectFactory,
    PropertyFactory,
)
from world.mechanics.models import ChallengeInstance, CharacterChallengeRecord, ObjectProperty
from world.mechanics.types import CapabilitySource, ChallengeResolutionError
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
        cls.consequence = ChallengeConsequenceFactory(
            challenge_template=cls.template,
            outcome_tier=cls.outcome,
            label="Gate burns down",
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

        # Template-level consequences
        cls.success_consequence = ChallengeConsequenceFactory(
            challenge_template=cls.template,
            outcome_tier=cls.outcome_success,
            label="Template success",
            weight=1,
        )
        cls.failure_consequence = ChallengeConsequenceFactory(
            challenge_template=cls.template,
            outcome_tier=cls.outcome_failure,
            label="Template failure",
            weight=1,
        )

    def test_selects_matching_tier(self) -> None:
        """Selects consequence matching the outcome tier."""
        from world.mechanics.challenge_resolution import _select_consequence

        result = _select_consequence(
            self.approach,
            self.template,
            self.outcome_success,
            ObjectDB.objects.create(db_key="SelChar1"),
        )
        assert result.label == "Template success"

    def test_approach_consequence_overrides_template(self) -> None:
        """Approach-level consequence overrides template-level for same tier."""
        from world.mechanics.challenge_resolution import _select_consequence

        ApproachConsequenceFactory(
            approach=self.approach,
            outcome_tier=self.outcome_success,
            label="Approach success override",
            weight=1,
        )
        result = _select_consequence(
            self.approach,
            self.template,
            self.outcome_success,
            ObjectDB.objects.create(db_key="SelChar2"),
        )
        assert result.label == "Approach success override"

    def test_fallback_when_no_consequences(self) -> None:
        """Creates fallback consequence when no tier matches."""
        from world.mechanics.challenge_resolution import _select_consequence

        other_outcome = CheckOutcomeFactory(name="CritSuccess_sel", success_level=2)
        result = _select_consequence(
            self.approach,
            self.template,
            other_outcome,
            ObjectDB.objects.create(db_key="SelChar3"),
        )
        assert result.label == "CritSuccess_sel"
        assert result.pk is None  # Unsaved fallback


class EffectHandlerTests(TestCase):
    """Tests for consequence effect handlers."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="EffectChar")
        cls.location = ObjectDB.objects.create(db_key="EffectRoom")
        cls.template = ChallengeTemplateFactory(name="EffectChallenge")
        cls.outcome = CheckOutcomeFactory(name="Success_eff", success_level=1)
        cls.consequence = ChallengeConsequenceFactory(
            challenge_template=cls.template,
            outcome_tier=cls.outcome,
            label="Effect test",
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
        result = apply_effect(effect, self.character, self.challenge)
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
        result = apply_effect(effect, self.character, self.challenge)
        assert result.applied is True
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
        result = apply_effect(effect, self.character, self.challenge)
        assert result.applied is True
        assert not ObjectProperty.objects.filter(
            object=self.location,
            property=prop,
        ).exists()

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
        result = apply_effect(effect, self.character, self.challenge)
        assert result.applied is False
        assert result.skip_reason != ""
