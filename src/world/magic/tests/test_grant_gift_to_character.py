"""Tests for the shared gift-minting primitive grant_gift_to_character (#1579).

Shared by path-crossing grants (#1579) and species-gift provisioning (#1580) so
there is one place that mints a CharacterGift + its latent GIFT thread.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.exceptions import GiftResonanceUnresolvable
from world.magic.factories import CharacterResonanceFactory, GiftFactory, ResonanceFactory
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

    def test_no_resonance_still_provisions_a_thread_when_one_resolves(self):
        """#2971: ``resonance=None`` no longer skips thread provisioning — it
        resolves a default instead. A fresh sheet with no claims, threads, or
        anima ritual has nothing to resolve from, so grant a claimed resonance
        first so the resolver has something to fall back to."""
        sheet = CharacterSheetFactory()
        CharacterResonanceFactory(character_sheet=sheet, resonance=self.res, lifetime_earned=1)

        _, created = grant_gift_to_character(sheet, self.gift, resonance=None)

        self.assertTrue(created)
        self.assertTrue(self._has_thread(sheet))

    def test_no_resonance_and_nothing_to_resolve_raises(self):
        """#2971: with nothing to resolve a resonance from, the grant raises
        ``GiftResonanceUnresolvable`` rather than silently skipping the thread."""
        sheet = CharacterSheetFactory()

        with self.assertRaises(GiftResonanceUnresolvable):
            grant_gift_to_character(sheet, self.gift, resonance=None)
