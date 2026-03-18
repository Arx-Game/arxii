"""Tests for challenge resolution service."""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.conditions.factories import CapabilityTypeFactory
from world.mechanics.constants import CapabilitySourceType
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeConsequenceFactory,
    ChallengeTemplateFactory,
    ChallengeTemplatePropertyFactory,
    PropertyFactory,
)
from world.mechanics.models import ChallengeInstance, CharacterChallengeRecord
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
