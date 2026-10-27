"""Actions for the drift correction rite (#4733): perform and decline."""

from __future__ import annotations

from actions.definitions.drift_correction import (
    DeclineDriftCorrectionAction,
    PerformDriftCorrectionAction,
)
from actions.registry import get_action
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.items.factories import ItemInstanceFactory
from world.magic.models import DriftConversionOffer, DriftCorrectionOutcomeShare
from world.magic.tests.test_drift_correction_rite import DriftRiteTestBase, _consumed


class DriftActionTestBase(DriftRiteTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.actor = self.sheet.character
        # The rite's offering must be carried by the performer.
        self.component.holder_character_sheet = self.sheet
        self.component.save(update_fields=["holder_character_sheet"])

    def perform(self, tier="Success", **overrides):
        kwargs = {
            "offer": self.offer,
            "source_resonance": self.dread,
            "target_resonance": self.dawnlight,
            "amount": 12,
            "components_provided": [self.component],
        }
        kwargs.update(overrides)
        with force_check_outcome(self.outcomes[tier]):
            return PerformDriftCorrectionAction().run(actor=self.actor, **kwargs)


class PerformDriftCorrectionActionTests(DriftActionTestBase):
    def test_registered_under_its_keys(self) -> None:
        self.assertIsInstance(get_action("perform_drift_correction"), PerformDriftCorrectionAction)
        self.assertIsInstance(get_action("decline_drift_correction"), DeclineDriftCorrectionAction)

    def test_success_states_what_moved(self) -> None:
        result = self.perform()
        self.assertTrue(result.success, result.message)
        self.assertEqual(result.message, "12 Drift Dread became 6 Drift Dawnlight.")
        rite = result.data["drift_correction_result"]
        self.assertEqual((rite.converted_amount, rite.granted_amount), (12, 6))
        self.assertTrue(_consumed(self.component_pk))

    def test_failed_roll_says_nothing_converted(self) -> None:
        self.set_shares(Failure="0.00")
        result = self.perform(tier="Failure")
        self.assertTrue(result.success, result.message)
        self.assertEqual(result.message, "The rite fails; nothing is converted.")
        self.assertEqual(result.data["drift_correction_result"].converted_amount, 0)

    def test_invalid_amount_surfaces_the_service_message(self) -> None:
        result = self.perform(amount=99)
        self.assertFalse(result.success)
        self.assertEqual(result.message, "You may convert at most 12 toward that resonance.")

    def test_unconfigured_share_surfaces_the_service_message(self) -> None:
        DriftCorrectionOutcomeShare.objects.filter(outcome_tier=self.outcomes["Success"]).delete()
        result = self.perform()
        self.assertFalse(result.success)
        self.assertEqual(result.message, "The rite of correction is not set up yet; tell staff.")

    def test_no_cap_toward_the_target_surfaces_the_service_message(self) -> None:
        result = self.perform(target_resonance=self.sunrise)
        self.assertFalse(result.success)
        self.assertEqual(
            result.message, "You have no open chance to correct drift toward that resonance."
        )

    def test_missing_offering_surfaces_the_component_message(self) -> None:
        result = self.perform(components_provided=[])
        self.assertFalse(result.success)
        self.assertIn("offering for Drift Dawnlight", result.message)
        self.assertTrue(DriftConversionOffer.objects.filter(pk=self.offer.pk).exists())

    def test_item_held_by_someone_else_is_refused_and_untouched(self) -> None:
        foreign = ItemInstanceFactory(template=self.component.template)
        result = self.perform(components_provided=[foreign])
        self.assertFalse(result.success)
        self.assertEqual(result.message, "You are not carrying everything you offered.")
        self.assertFalse(_consumed(foreign.pk))
        self.assertEqual(self.cap_value(), 12)

    def test_another_characters_offer_is_refused(self) -> None:
        stranger = CharacterSheetFactory().character
        with force_check_outcome(self.outcomes["Success"]):
            result = PerformDriftCorrectionAction().run(
                actor=stranger,
                offer=self.offer,
                source_resonance=self.dread,
                target_resonance=self.dawnlight,
                amount=12,
                components_provided=[self.component],
            )
        self.assertFalse(result.success)
        self.assertEqual(result.message, "That chance to correct drift is not yours.")
        self.assertEqual(self.cap_value(), 12)


class DeclineDriftCorrectionActionTests(DriftActionTestBase):
    def test_decline_deletes_the_offer(self) -> None:
        result = DeclineDriftCorrectionAction().run(actor=self.actor, offer=self.offer)
        self.assertTrue(result.success, result.message)
        self.assertFalse(DriftConversionOffer.objects.filter(pk=self.offer.pk).exists())

    def test_decline_of_another_characters_offer_is_refused(self) -> None:
        stranger = CharacterSheetFactory().character
        result = DeclineDriftCorrectionAction().run(actor=stranger, offer=self.offer)
        self.assertFalse(result.success)
        self.assertTrue(DriftConversionOffer.objects.filter(pk=self.offer.pk).exists())
