"""Model rules for being pacts (#4341): constraints and clean() checks."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.pacts.constants import CharacterPactCommitmentKind, CharacterPactEnding
from world.pacts.factories import (
    CharacterPactFactory,
    PactOfferCommitmentFactory,
    PactOfferFactory,
)
from world.pacts.models import CharacterPact
from world.worship.factories import PledgeFactory


class CharacterPactConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.pact = CharacterPactFactory()

    def test_one_active_pact_per_standing(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            CharacterPact.objects.create(
                character_sheet=self.pact.character_sheet,
                offer=self.pact.offer,
                devotion_standing=self.pact.devotion_standing,
            )

    def test_a_dissolved_pact_frees_the_standing(self) -> None:
        self.pact.dissolved_at = timezone.now()
        self.pact.dissolution_reason = CharacterPactEnding.RENOUNCED
        self.pact.save()
        renewed = CharacterPact.objects.create(
            character_sheet=self.pact.character_sheet,
            offer=self.pact.offer,
            devotion_standing=self.pact.devotion_standing,
        )
        self.assertTrue(renewed.is_active)
        self.assertFalse(self.pact.is_active)

    def test_reason_is_set_exactly_when_dissolved(self) -> None:
        self.pact.dissolution_reason = CharacterPactEnding.BREACH
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.pact.save()
        self.pact.dissolution_reason = ""
        self.pact.dissolved_at = timezone.now()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.pact.save()


class PactCleanTests(TestCase):
    def test_offer_condition_needs_two_threshold_stages(self) -> None:
        condition = ConditionTemplateFactory(has_progression=True)
        ConditionStageFactory(condition=condition, stage_order=1, severity_threshold=1)
        offer = PactOfferFactory.build(condition=condition)
        with self.assertRaisesMessage(ValidationError, "at least two stages"):
            offer.clean()
        ConditionStageFactory(condition=condition, stage_order=2, severity_threshold=11)
        offer.clean()

    def test_offer_condition_must_progress(self) -> None:
        offer = PactOfferFactory.build(condition=ConditionTemplateFactory(has_progression=False))
        with self.assertRaisesMessage(ValidationError, "progress through stages"):
            offer.clean()

    def test_commitment_rules(self) -> None:
        offer = PactOfferFactory()
        favor = PactOfferCommitmentFactory.build(offer=offer, amount=0)
        custom = PactOfferCommitmentFactory.build(
            offer=offer, kind=CharacterPactCommitmentKind.CUSTOM, notes=" "
        )
        owed_by_other = PactOfferCommitmentFactory.build(offer=offer, owed_by_holder=False)
        for commitment, field in (
            (favor, "amount"),
            (custom, "notes"),
            (owed_by_other, "owed_by_holder"),
        ):
            with self.subTest(field=field), self.assertRaises(ValidationError) as ctx:
                commitment.clean()
            self.assertIn(field, ctx.exception.message_dict)

    def test_pledge_offer_must_be_from_its_being(self) -> None:
        pledge = PledgeFactory()
        pledge.pact_offer = PactOfferFactory()
        with self.assertRaises(ValidationError) as ctx:
            pledge.clean()
        self.assertIn("pact_offer", ctx.exception.message_dict)
        pledge.pact_offer = PactOfferFactory(being=pledge.being)
        pledge.clean()
