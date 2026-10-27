"""Models behind drift correction (#4733): offers, caps, config, outcome shares."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemTemplateFactory
from world.magic.constants import GainSource
from world.magic.factories import (
    DriftConversionCapFactory,
    DriftConversionOfferFactory,
    DriftCorrectionConfigFactory,
    DriftCorrectionOutcomeShareFactory,
    DriftCorrectionRiteFactory,
    ResonanceFactory,
    RitualComponentRequirementFactory,
    RitualFactory,
)
from world.magic.models import (
    DriftCorrectionConfig,
    ResonanceGrant,
    RitualComponentRequirement,
)
from world.scenes.factories import SceneFactory
from world.traits.factories import CheckOutcomeFactory


class DriftConversionOfferTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.scene = SceneFactory()

    def test_one_offer_per_sheet_and_scene(self):
        DriftConversionOfferFactory(character_sheet=self.sheet, scene=self.scene)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DriftConversionOfferFactory(character_sheet=self.sheet, scene=self.scene)

    def test_same_sheet_other_scene_is_allowed(self):
        DriftConversionOfferFactory(character_sheet=self.sheet, scene=self.scene)
        offer = DriftConversionOfferFactory(character_sheet=self.sheet, scene=SceneFactory())
        self.assertEqual(offer.character_sheet, self.sheet)

    def test_one_cap_per_offer_and_target(self):
        offer = DriftConversionOfferFactory(character_sheet=self.sheet, scene=self.scene)
        target = ResonanceFactory()
        DriftConversionCapFactory(offer=offer, target_resonance=target)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DriftConversionCapFactory(offer=offer, target_resonance=target)

    def test_cap_names_the_grants_it_may_convert(self):
        offer = DriftConversionOfferFactory(character_sheet=self.sheet, scene=self.scene)
        cap = DriftConversionCapFactory(offer=offer, cap=12)
        grant = ResonanceGrant.objects.create(
            character_sheet=self.sheet,
            resonance=cap.target_resonance,
            amount=12,
            source=GainSource.STAFF_GRANT,
        )
        cap.grants.add(grant)
        self.assertEqual(list(offer.caps.get().grants.all()), [grant])


class DriftCorrectionConfigTests(TestCase):
    def test_defaults_are_valid_before_staff_author_the_row(self):
        config = DriftCorrectionConfig.objects.create(pk=1)
        config.full_clean()
        self.assertIsNone(config.rite)
        self.assertIsNone(config.check_type)
        self.assertEqual(config.check_difficulty, 0)
        self.assertEqual(config.cap_percent, 50)

    def test_cap_percent_over_one_hundred_is_invalid(self):
        config = DriftCorrectionConfig(pk=1, cap_percent=101)
        with self.assertRaises(ValidationError) as ctx:
            config.full_clean()
        self.assertIn("cap_percent", ctx.exception.message_dict)

    def test_factory_returns_the_single_row(self):
        first = DriftCorrectionConfigFactory()
        self.assertEqual(DriftCorrectionConfigFactory().pk, first.pk)
        self.assertEqual(DriftCorrectionConfig.objects.cached_singleton(), first)

    def test_rite_factory_builds_a_client_hosted_service_ritual(self):
        rite = DriftCorrectionRiteFactory()
        rite.full_clean()
        self.assertTrue(rite.client_hosted)
        self.assertEqual(
            rite.service_function_path,
            "world.magic.services.drift_correction.perform_drift_correction_rite",
        )
        requirement = rite.requirements.get()
        self.assertTrue(requirement.matches_target_resonance)


class DriftCorrectionOutcomeShareTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.poor = CheckOutcomeFactory(name="Drift poor", success_level=-1)
        cls.good = CheckOutcomeFactory(name="Drift good", success_level=1)

    def test_better_tier_with_lower_share_is_rejected(self):
        DriftCorrectionOutcomeShareFactory(outcome_tier=self.poor, converted_share=Decimal("0.60"))
        better = DriftCorrectionOutcomeShareFactory.build(
            outcome_tier=self.good, converted_share=Decimal("0.40")
        )
        with self.assertRaises(ValidationError) as ctx:
            better.full_clean()
        self.assertIn("converted_share", ctx.exception.message_dict)

    def test_equal_share_across_tiers_is_accepted(self):
        DriftCorrectionOutcomeShareFactory(outcome_tier=self.poor, converted_share=Decimal("0.60"))
        equal = DriftCorrectionOutcomeShareFactory.build(
            outcome_tier=self.good, converted_share=Decimal("0.60")
        )
        equal.full_clean()

    def test_worse_tier_with_higher_share_than_a_better_tier_is_rejected(self):
        DriftCorrectionOutcomeShareFactory(outcome_tier=self.good, converted_share=Decimal("0.50"))
        worse = DriftCorrectionOutcomeShareFactory.build(
            outcome_tier=self.poor, converted_share=Decimal("0.70")
        )
        with self.assertRaises(ValidationError):
            worse.full_clean()

    def test_share_above_one_is_rejected(self):
        share = DriftCorrectionOutcomeShareFactory.build(
            outcome_tier=self.good, converted_share=Decimal("1.50")
        )
        with self.assertRaises(ValidationError):
            share.full_clean()


class RitualComponentRequirementModeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ritual = RitualFactory()

    def test_target_resonance_mode_alone_is_valid(self):
        requirement = RitualComponentRequirement(
            ritual=self.ritual, matches_target_resonance=True, quantity=1
        )
        requirement.full_clean()

    def test_template_and_target_resonance_together_is_invalid(self):
        requirement = RitualComponentRequirement(
            ritual=self.ritual,
            item_template=ItemTemplateFactory(),
            matches_target_resonance=True,
        )
        with self.assertRaises(ValidationError):
            requirement.full_clean()

    def test_no_mode_is_invalid(self):
        requirement = RitualComponentRequirement(ritual=self.ritual)
        with self.assertRaises(ValidationError):
            requirement.full_clean()

    def test_min_item_meaning_requires_target_resonance_mode(self):
        requirement = RitualComponentRequirement(
            ritual=self.ritual, item_template=ItemTemplateFactory(), min_item_meaning=3
        )
        with self.assertRaises(ValidationError):
            requirement.full_clean()

    def test_min_item_meaning_with_target_resonance_mode_is_valid(self):
        requirement = RitualComponentRequirement(
            ritual=self.ritual, matches_target_resonance=True, min_item_meaning=3
        )
        requirement.full_clean()

    def test_min_item_meaning_of_zero_is_invalid(self):
        requirement = RitualComponentRequirement(
            ritual=self.ritual, matches_target_resonance=True, min_item_meaning=0
        )
        with self.assertRaises(ValidationError) as ctx:
            requirement.full_clean()
        self.assertIn("min_item_meaning", ctx.exception.message_dict)

    def test_target_mode_reads_as_a_target_resonance_item_not_none(self):
        requirement = RitualComponentRequirement(
            ritual=self.ritual, matches_target_resonance=True, quantity=2
        )
        text = str(requirement)
        self.assertIn("target resonance", text)
        self.assertNotIn("None", text)

    def test_template_mode_still_builds_from_the_factory(self):
        requirement = RitualComponentRequirementFactory(ritual=self.ritual)
        requirement.full_clean()
        self.assertFalse(requirement.matches_target_resonance)


class DriftCorrectionGrantShapeTests(TestCase):
    def test_grant_with_no_typed_source_is_accepted(self):
        sheet = CharacterSheetFactory()
        grant = ResonanceGrant.objects.create(
            character_sheet=sheet,
            resonance=ResonanceFactory(),
            amount=5,
            source=GainSource.DRIFT_CORRECTION,
        )
        self.assertEqual(grant.source, GainSource.DRIFT_CORRECTION)

    def test_grant_with_a_typed_source_fk_is_refused_by_the_database(self):
        sheet = CharacterSheetFactory()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ResonanceGrant.objects.create(
                character_sheet=sheet,
                resonance=ResonanceFactory(),
                amount=5,
                source=GainSource.DRIFT_CORRECTION,
                source_staff_account=AccountFactory(),
            )
