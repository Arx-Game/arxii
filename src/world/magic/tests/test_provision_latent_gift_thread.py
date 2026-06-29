"""provision_latent_gift_thread + gift_resonances_for + resolve_specialized_variant."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import GiftFactory, ResonanceFactory, TechniqueFactory
from world.magic.models import Thread
from world.magic.specialization.models import TechniqueVariant
from world.magic.specialization.services import (
    gift_resonances_for,
    provision_latent_gift_thread,
    resolve_specialized_variant,
)


class ProvisionLatentGiftThreadTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        cls.resonance = ResonanceFactory()
        cls.gift.resonances.add(cls.resonance)

    def test_provision_creates_level_0_gift_thread(self) -> None:
        provision_latent_gift_thread(self.sheet, self.gift, resonance=self.resonance)
        thread = Thread.objects.get(
            owner=self.sheet,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
        )
        self.assertEqual(thread.level, 0)
        self.assertEqual(thread.resonance, self.resonance)
        self.assertIsNone(thread.retired_at)

    def test_provision_idempotent(self) -> None:
        provision_latent_gift_thread(self.sheet, self.gift, resonance=self.resonance)
        provision_latent_gift_thread(self.sheet, self.gift, resonance=self.resonance)
        self.assertEqual(
            Thread.objects.filter(
                owner=self.sheet,
                target_kind=TargetKind.GIFT,
                target_gift=self.gift,
            ).count(),
            1,
        )


class GiftResonancesForTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        cls.resonance = ResonanceFactory()
        cls.gift.resonances.add(cls.resonance)

    def test_returns_thread_resonance_when_owned(self) -> None:
        provision_latent_gift_thread(self.sheet, self.gift, resonance=self.resonance)
        result = gift_resonances_for(self.sheet.character, self.gift)
        self.assertEqual([r.pk for r in result], [self.resonance.pk])

    def test_falls_back_to_supported_set_when_no_thread(self) -> None:
        # No thread -> fall back to gift.resonances (the supported set).
        result = gift_resonances_for(self.sheet.character, self.gift)
        self.assertEqual([r.pk for r in result], [self.resonance.pk])


class ResolveSpecializedVariantTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        cls.resonance = ResonanceFactory()
        cls.gift.resonances.add(cls.resonance)
        cls.technique = TechniqueFactory(gift=cls.gift)

    def test_resolves_parent_when_thread_below_threshold(self) -> None:
        provision_latent_gift_thread(self.sheet, self.gift, resonance=self.resonance)
        # thread level 0, variant unlock 3 -> parent technique
        result = resolve_specialized_variant(entity=self.technique, character=self.sheet.character)
        self.assertEqual(result, self.technique)

    def test_resolves_variant_when_thread_crosses_threshold(self) -> None:
        from world.magic.factories import ThreadFactory

        TechniqueVariant.objects.create(
            parent_technique=self.technique,
            resonance=self.resonance,
            unlock_thread_level=3,
            name_override="Celestial Form",
            intensity_delta=5,
        )
        ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            target_trait=None,
            level=5,
        )
        result = resolve_specialized_variant(entity=self.technique, character=self.sheet.character)
        # The resolver returns a _ResolvedTechnique wrapper when a variant
        # matches; its ``name`` property surfaces the variant's name_override.
        self.assertEqual(result.name, "Celestial Form")
