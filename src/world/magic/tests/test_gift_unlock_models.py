"""Model tests for gift acquisition models (#1587)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.magic.constants import GiftKind
from world.magic.factories import GiftFactory
from world.magic.models import (
    CharacterGiftUnlock,
    GiftAcquisitionConfig,
    GiftUnlock,
    TechniqueTeachingOffer,
)


class GiftUnlockModelTest(TestCase):
    def test_clean_rejects_major_gift(self):
        major_gift = GiftFactory(kind=GiftKind.MAJOR)
        unlock = GiftUnlock(gift=major_gift, xp_cost=10)
        with self.assertRaises(ValidationError):
            unlock.clean()

    def test_clean_accepts_minor_gift(self):
        minor_gift = GiftFactory(kind=GiftKind.MINOR)
        unlock = GiftUnlock(gift=minor_gift, xp_cost=10)
        unlock.clean()  # should not raise

    def test_str(self):
        gift = GiftFactory(kind=GiftKind.MINOR, name="Sight")
        unlock = GiftUnlock(gift=gift, xp_cost=10)
        self.assertIn("Sight", str(unlock))


class CharacterGiftUnlockModelTest(TestCase):
    def test_unique_together(self):
        from django.db import IntegrityError

        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        gift = GiftFactory(kind=GiftKind.MINOR)
        unlock = GiftUnlock.objects.create(gift=gift, xp_cost=10)
        CharacterGiftUnlock.objects.create(character=sheet, unlock=unlock, xp_spent=10)
        with self.assertRaises(IntegrityError):
            CharacterGiftUnlock.objects.create(character=sheet, unlock=unlock, xp_spent=10)


class GiftAcquisitionConfigModelTest(TestCase):
    def test_defaults(self):
        config = GiftAcquisitionConfig.objects.create()
        self.assertEqual(config.techniques_per_thread_level, 3)
        self.assertEqual(config.first_technique_ap_multiplier, 3)


class TechniqueTeachingOfferModelTest(TestCase):
    def test_str(self):
        from world.magic.factories import TechniqueFactory
        from world.roster.factories import RosterTenureFactory

        gift = GiftFactory(kind=GiftKind.MINOR)
        technique = TechniqueFactory(gift=gift, name="Soulsight")
        teacher = RosterTenureFactory()
        offer = TechniqueTeachingOffer(
            teacher=teacher,
            technique=technique,
            pitch="I will teach you",
            learn_ap_cost=5,
            banked_ap=1,
        )
        self.assertIn("teaches", str(offer))
        self.assertIn("Soulsight", str(offer))


class GiftAcquisitionConfigGetterTest(TestCase):
    def test_get_creates_singleton(self):
        from world.magic.services.gift_acquisition import get_gift_acquisition_config

        GiftAcquisitionConfig.objects.all().delete()
        config = get_gift_acquisition_config()
        self.assertEqual(config.pk, 1)
        self.assertEqual(config.techniques_per_thread_level, 3)
        # Idempotent
        config2 = get_gift_acquisition_config()
        self.assertEqual(config2.pk, 1)
