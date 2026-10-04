"""Minor-gift ultimates in the Audere reveal (#4118)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.classes.factories import PathFactory
from world.covenants.constants import RoleArchetype
from world.magic.admin import GiftAdminForm
from world.magic.constants import GiftKind, UltimateCardKind, UltimateSource
from world.magic.factories import CharacterGiftFactory, GiftFactory, UltimateTechniqueFactory
from world.magic.models import KnownUltimate
from world.magic.services.ultimates import (
    choose_ultimate,
    clear_readied_ultimate,
    ultimate_reveal_for,
)
from world.magic.tests.test_ultimate_reveal import _RevealFixture
from world.progression.factories import CharacterPathHistoryFactory
from world.worship.factories import DevotionStandingFactory, WorshippedBeingFactory
from world.worship.models import PatronageValence


class _MinorFixture(_RevealFixture):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.minor = GiftFactory(kind=GiftKind.MINOR)
        cls.minor_ultimate = UltimateTechniqueFactory(
            gift=cls.minor, name="Minor Bulwark", archetype_alignment=RoleArchetype.SHIELD
        )
        cls.minor.ultimate_techniques.add(cls.minor_ultimate)
        cls.minor_row = CharacterGiftFactory(character=cls.sheet, gift=cls.minor)

    def _gift_groups(self) -> list:
        reveal = ultimate_reveal_for(self.sheet)
        return [g for g in reveal.groups if g.source == UltimateSource.GIFT]


class GiftPoolTests(_MinorFixture):
    def test_held_minor_gift_adds_gift_group(self) -> None:
        (group,) = self._gift_groups()
        self.assertEqual(group.source_id, self.minor.pk)
        self.assertEqual(group.gift, self.minor)
        (card,) = group.cards
        self.assertEqual(card.kind, UltimateCardKind.CATEGORY)
        self.assertEqual(card.label, "Wall")

    def test_minor_gift_without_ultimates_yields_no_group(self) -> None:
        self.minor.ultimate_techniques.clear()
        self.assertEqual(self._gift_groups(), [])

    def test_unheld_minor_gift_yields_no_group(self) -> None:
        self.minor_row.delete()
        self.assertEqual(self._gift_groups(), [])

    def test_held_major_gift_with_ultimates_yields_no_gift_group(self) -> None:
        major = GiftFactory(kind=GiftKind.MAJOR)
        CharacterGiftFactory(character=self.sheet, gift=major)
        # Direct add skips Gift.clean(), so the pool filter is the only guard here.
        major.ultimate_techniques.add(
            UltimateTechniqueFactory(gift=major, archetype_alignment=RoleArchetype.SWORD)
        )
        for group in self._gift_groups():
            self.assertNotEqual(group.gift, major)
        self.assertEqual([g.gift for g in self._gift_groups()], [self.minor])

    def test_choice_then_known_listed_in_same_group(self) -> None:
        (group,) = self._gift_groups()
        choose_ultimate(self.sheet, group.cards[0].choice_key)
        self.assertTrue(
            KnownUltimate.objects.filter(character=self.sheet, technique=self.minor_ultimate)
        )
        clear_readied_ultimate(self.sheet)
        (group,) = self._gift_groups()
        known = [c for c in group.cards if c.kind == UltimateCardKind.KNOWN]
        self.assertEqual([c.technique for c in known], [self.minor_ultimate])

    def test_path_change_keeps_group(self) -> None:
        CharacterPathHistoryFactory(character=self.sheet, path=PathFactory())
        self.assertEqual(len(self._gift_groups()), 1)

    def test_technique_also_in_patron_pool_appears_once(self) -> None:
        being = WorshippedBeingFactory()
        being.ultimate_techniques.add(self.minor_ultimate)
        DevotionStandingFactory(
            character_sheet=self.sheet, being=being, valence=PatronageValence.DEVOTIONAL
        )
        reveal = ultimate_reveal_for(self.sheet)
        sources = [g.source for g in reveal.groups]
        # Pool order puts the patron ahead of the gift: the earlier pool keeps it.
        self.assertEqual(sources.count(UltimateSource.PATRON), 1)
        self.assertNotIn(UltimateSource.GIFT, sources)


class GiftCleanTests(TestCase):
    def test_major_gift_with_ultimates_rejected(self) -> None:
        gift = GiftFactory(kind=GiftKind.MAJOR)
        gift.ultimate_techniques.add(UltimateTechniqueFactory(gift=gift))
        with self.assertRaises(ValidationError) as ctx:
            gift.full_clean()
        self.assertIn("kind", ctx.exception.message_dict)

    def test_minor_gift_with_ultimates_passes(self) -> None:
        gift = GiftFactory(kind=GiftKind.MINOR)
        gift.ultimate_techniques.add(UltimateTechniqueFactory(gift=gift))
        gift.full_clean()


class GiftAdminFormTests(TestCase):
    def _form(self, gift, techniques, kind=None):
        data = {
            "name": gift.name,
            "kind": kind or gift.kind,
            "description": gift.description,
            "ultimate_techniques": [t.pk for t in techniques],
        }
        return GiftAdminForm(data=data, instance=gift)

    def test_valid_minor_ultimates(self) -> None:
        gift = GiftFactory(kind=GiftKind.MINOR)
        form = self._form(gift, [UltimateTechniqueFactory(gift=gift)])
        form.is_valid()
        self.assertNotIn("ultimate_techniques", form.errors)

    def test_foreign_gift_ultimate_rejected(self) -> None:
        gift = GiftFactory(kind=GiftKind.MINOR)
        form = self._form(gift, [UltimateTechniqueFactory(gift=GiftFactory())])
        form.is_valid()
        self.assertEqual(
            form.errors["ultimate_techniques"], ["Every ultimate must belong to this gift."]
        )

    def test_major_gift_ultimates_rejected(self) -> None:
        gift = GiftFactory(kind=GiftKind.MAJOR)
        form = self._form(gift, [UltimateTechniqueFactory(gift=gift)])
        form.is_valid()
        self.assertEqual(
            form.errors["ultimate_techniques"], ["Only a minor gift carries ultimates here."]
        )
