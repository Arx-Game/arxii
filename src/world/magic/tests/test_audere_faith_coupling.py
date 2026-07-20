"""Tests for Audere Majora faith coupling (#2360)."""

from django.db import IntegrityError
from django.test import TestCase

from world.magic.audere_majora import (
    AudereMajoraFaithVariant,
)
from world.worship.factories import WorshippedBeingFactory


def _make_threshold(suffix: str = ""):
    """Create a minimal AudereMajoraThreshold for testing."""
    from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
    from world.magic.audere_majora import AudereMajoraThreshold
    from world.magic.factories import IntensityTierFactory

    tier = IntensityTierFactory(name=f"Tier_{suffix}", threshold=10)
    soulfray_template = ConditionTemplateFactory(name=f"Soulfray_{suffix}", has_progression=True)
    stage = ConditionStageFactory(
        condition=soulfray_template,
        stage_order=3,
        name=f"Stage3_{suffix}",
    )
    return AudereMajoraThreshold.objects.create(
        boundary_level=5,
        target_stage=2,
        minimum_intensity_tier=tier,
        minimum_warp_stage=stage,
        requires_active_audere=True,
        vision_text="[PLACEHOLDER]",
        manifestation_text="[PLACEHOLDER]",
    )


class _FakeOffer:
    """Minimal stand-in for PendingAudereMajoraOffer in service tests."""

    def __init__(self):
        self.faith_variant = None

    def save(self, **kwargs):
        pass


class FaithVariantModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.threshold = _make_threshold("1")
        cls.being = WorshippedBeingFactory()

    def test_create_variant(self) -> None:
        variant = AudereMajoraFaithVariant.objects.create(
            threshold=self.threshold,
            being=self.being,
            vision_text="[PLACEHOLDER] Your god's vision.",
            manifestation_text="[PLACEHOLDER] A divine manifestation.",
            resonance_pool_cost=200,
            favor_threshold=50,
        )
        self.assertIn(str(self.threshold), str(variant))

    def test_unique_per_threshold_being(self) -> None:
        AudereMajoraFaithVariant.objects.create(
            threshold=self.threshold,
            being=self.being,
            vision_text="a",
            manifestation_text="b",
            resonance_pool_cost=100,
        )
        with self.assertRaises(IntegrityError):
            AudereMajoraFaithVariant.objects.create(
                threshold=self.threshold,
                being=self.being,
                vision_text="c",
                manifestation_text="d",
                resonance_pool_cost=100,
            )


class FaithCouplingServiceTests(TestCase):
    """Tests for maybe_apply_audere_faith_coupling (#2360)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory

        cls.threshold = _make_threshold("2")
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.being = WorshippedBeingFactory(resonance_pool=500)
        cls.variant = AudereMajoraFaithVariant.objects.create(
            threshold=cls.threshold,
            being=cls.being,
            vision_text="[PLACEHOLDER] faith vision",
            manifestation_text="[PLACEHOLDER] faith manifestation",
            resonance_pool_cost=200,
            favor_threshold=50,
        )

    def test_no_variant_when_no_devotion(self) -> None:
        from world.magic.audere_majora import maybe_apply_audere_faith_coupling

        offer = _FakeOffer()
        result = maybe_apply_audere_faith_coupling(self.sheet, self.threshold, offer)
        self.assertIsNone(result)

    def test_variant_selected_when_devotion_meets_threshold(self) -> None:
        from world.magic.audere_majora import maybe_apply_audere_faith_coupling
        from world.worship.models import DevotionStanding

        DevotionStanding.objects.create(
            character_sheet=self.sheet,
            being=self.being,
            favor=75,
        )
        offer = _FakeOffer()
        result = maybe_apply_audere_faith_coupling(self.sheet, self.threshold, offer)
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, self.variant.pk)

    def test_no_variant_when_pool_insufficient(self) -> None:
        from world.magic.audere_majora import maybe_apply_audere_faith_coupling
        from world.worship.models import DevotionStanding

        DevotionStanding.objects.create(
            character_sheet=self.sheet,
            being=self.being,
            favor=75,
        )
        self.being.resonance_pool = 50
        self.being.save()
        offer = _FakeOffer()
        result = maybe_apply_audere_faith_coupling(self.sheet, self.threshold, offer)
        self.assertIsNone(result)
