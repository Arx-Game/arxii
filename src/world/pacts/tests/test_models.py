"""Model rules for being pacts (#4341): the clean() checks no journey reaches."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.pacts.constants import CharacterPactCommitmentKind
from world.pacts.factories import PactOfferCommitmentFactory, PactOfferFactory


class PactCleanTests(TestCase):
    """The offer's and the commitment's clean() refusals.

    A journey cannot reach them: staff author offers and commitments in the Being
    Service builder and the admin, whose forms run these branches, and no play path
    writes either row. The builder journey saves only valid rows.
    """

    def test_offer_condition_must_progress_through_two_threshold_stages(self) -> None:
        offer = PactOfferFactory.build(condition=ConditionTemplateFactory(has_progression=False))
        with self.assertRaisesMessage(ValidationError, "progress through stages"):
            offer.clean()
        condition = ConditionTemplateFactory(has_progression=True)
        ConditionStageFactory(condition=condition, stage_order=1, severity_threshold=1)
        offer = PactOfferFactory.build(condition=condition)
        with self.assertRaisesMessage(ValidationError, "at least two stages"):
            offer.clean()
        ConditionStageFactory(condition=condition, stage_order=2, severity_threshold=11)
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
