"""Tests for the shared gift-minting primitive grant_gift_to_character (#1579).

Shared by path-crossing grants (#1579) and species-gift provisioning (#1580) so
there is one place that mints a CharacterGift + its latent GIFT thread.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import GiftFactory, ResonanceFactory
from world.magic.models import CharacterGift, Thread
from world.magic.specialization.services import grant_gift_to_character


class GrantGiftToCharacterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gift = GiftFactory(name="Aeromancy_ggtc")
        cls.res = ResonanceFactory(name="Gale_ggtc")

    def _has_thread(self, sheet):
        return Thread.objects.filter(
            owner=sheet, target_kind=TargetKind.GIFT, target_gift=self.gift
        ).exists()

    def test_mints_gift_and_latent_thread(self):
        sheet = CharacterSheetFactory()
        cg, created = grant_gift_to_character(sheet, self.gift, resonance=self.res)
        self.assertTrue(created)
        self.assertEqual(cg.character_id, sheet.pk)
        self.assertTrue(self._has_thread(sheet))

    def test_idempotent(self):
        sheet = CharacterSheetFactory()
        grant_gift_to_character(sheet, self.gift, resonance=self.res)
        _, created = grant_gift_to_character(sheet, self.gift, resonance=self.res)
        self.assertFalse(created)
        self.assertEqual(CharacterGift.objects.filter(character=sheet, gift=self.gift).count(), 1)

    def test_no_resonance_skips_thread(self):
        sheet = CharacterSheetFactory()
        _, created = grant_gift_to_character(sheet, self.gift, resonance=None)
        self.assertTrue(created)
        self.assertFalse(self._has_thread(sheet))
