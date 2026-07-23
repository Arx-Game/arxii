"""Tests for grant_path_magic (#1579, ADR-0055).

Crossing into a path grants its authored gift(s) + curated starter techniques.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import (
    CharacterGift,
    CharacterTechnique,
    PathGiftGrant,
    Thread,
)
from world.magic.services.path_magic import grant_path_magic


class GrantPathMagicTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.path = PathFactory(name="Steel Warden")
        cls.r1 = ResonanceFactory(name="Ember")
        cls.r2 = ResonanceFactory(name="Cinder")
        cls.gift = GiftFactory(name="Pyromancy")
        cls.gift.resonances.add(cls.r1, cls.r2)
        cls.tech_a = TechniqueFactory(name="Flame Lash", gift=cls.gift)
        cls.tech_b = TechniqueFactory(name="Cinder Ward", gift=cls.gift)
        cls.grant = PathGiftGrant.objects.create(path=cls.path, gift=cls.gift)
        cls.grant.starter_techniques.add(cls.tech_a, cls.tech_b)

    def _latent_thread(self, sheet):
        return Thread.objects.filter(
            owner=sheet, target_kind=TargetKind.GIFT, target_gift=self.gift
        ).first()

    def test_grants_gift_techniques_and_latent_thread(self):
        sheet = CharacterSheetFactory()
        result = grant_path_magic(sheet, self.path)

        self.assertTrue(CharacterGift.objects.filter(character=sheet, gift=self.gift).exists())
        owned = set(
            CharacterTechnique.objects.filter(character=sheet).values_list(
                "technique_id", flat=True
            )
        )
        self.assertEqual(owned, {self.tech_a.pk, self.tech_b.pk})
        self.assertIsNotNone(self._latent_thread(sheet))
        self.assertEqual(result.granted_gifts, [self.gift])
        self.assertEqual(
            {t.pk for t in result.granted_techniques}, {self.tech_a.pk, self.tech_b.pk}
        )

    def test_idempotent_second_call_grants_nothing(self):
        sheet = CharacterSheetFactory()
        grant_path_magic(sheet, self.path)
        again = grant_path_magic(sheet, self.path)

        self.assertEqual(again.granted_gifts, [])
        self.assertEqual(again.granted_techniques, [])
        self.assertEqual(CharacterTechnique.objects.filter(character=sheet).count(), 2)
        self.assertEqual(CharacterGift.objects.filter(character=sheet, gift=self.gift).count(), 1)

    def test_pre_owned_gift_not_relisted_but_techniques_granted(self):
        sheet = CharacterSheetFactory()
        CharacterGift.objects.create(character=sheet, gift=self.gift)

        result = grant_path_magic(sheet, self.path)

        self.assertEqual(result.granted_gifts, [])
        self.assertEqual(
            {t.pk for t in result.granted_techniques}, {self.tech_a.pk, self.tech_b.pk}
        )

    def test_resonance_prefers_claimed_resonance_in_supported_set(self):
        from world.magic.factories import CharacterResonanceFactory

        sheet = CharacterSheetFactory()
        CharacterResonanceFactory(character_sheet=sheet, resonance=self.r2)

        grant_path_magic(sheet, self.path)

        thread = self._latent_thread(sheet)
        self.assertEqual(thread.resonance_id, self.r2.pk)

    def test_resonance_falls_back_to_first_supported(self):
        sheet = CharacterSheetFactory()

        grant_path_magic(sheet, self.path)

        thread = self._latent_thread(sheet)
        self.assertIn(thread.resonance_id, {self.r1.pk, self.r2.pk})

    def test_cross_into_path_writes_history_and_grants(self):
        from world.progression.models import CharacterPathHistory
        from world.progression.services.advancement import cross_into_path

        sheet = CharacterSheetFactory()
        result = cross_into_path(sheet, self.path)

        self.assertTrue(
            CharacterPathHistory.objects.filter(character=sheet, path=self.path).exists()
        )
        self.assertEqual(
            {t.pk for t in result.granted_techniques}, {self.tech_a.pk, self.tech_b.pk}
        )

    def test_path_without_grant_is_noop(self):
        sheet = CharacterSheetFactory()
        empty_path = PathFactory(name="Pathless")

        result = grant_path_magic(sheet, empty_path)

        self.assertEqual(result.granted_gifts, [])
        self.assertEqual(result.granted_techniques, [])
        self.assertFalse(CharacterGift.objects.filter(character=sheet).exists())
