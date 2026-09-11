"""Model tests for the worship foundation (#2355)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import ResonanceFactory
from world.magic.models import Facet
from world.worship.constants import BeingResonanceTier
from world.worship.factories import (
    DevotionStandingFactory,
    WorshipDeclarationFactory,
    WorshippedBeingFactory,
    WorshipTraditionFactory,
)
from world.worship.models import BeingFacet, BeingNickname, BeingResonance


class WorshipModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tradition = WorshipTraditionFactory()
        cls.being = WorshippedBeingFactory(tradition=cls.tradition)
        cls.sheet = CharacterSheetFactory()

    def test_being_defaults(self) -> None:
        self.assertEqual(self.being.resonance_pool, 0)
        self.assertEqual(self.being.lifetime_worship, 0)
        self.assertIsNone(self.being.avatar_sheet)
        self.assertTrue(self.being.is_active)

    def test_devotion_standing_unique_per_sheet_and_being(self) -> None:
        DevotionStandingFactory(character_sheet=self.sheet, being=self.being)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            DevotionStandingFactory(character_sheet=self.sheet, being=self.being)

    def test_declaration_public_only(self) -> None:
        declaration = WorshipDeclarationFactory(character_sheet=self.sheet)
        self.assertIsNotNone(declaration.public_being)
        self.assertIsNone(declaration.secret_being)
        self.assertIsNone(declaration.secret)


class BeingFacetTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.being = WorshippedBeingFactory()

    def test_being_can_hold_multiple_facets(self) -> None:
        scythe = Facet.objects.create(name="Scythe")
        red = Facet.objects.create(name="Red")
        BeingFacet.objects.create(being=self.being, facet=scythe)
        BeingFacet.objects.create(being=self.being, facet=red)
        self.assertEqual(self.being.being_facets.count(), 2)

    def test_unique_per_being_and_facet(self) -> None:
        scythe = Facet.objects.create(name="Scythe")
        BeingFacet.objects.create(being=self.being, facet=scythe)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            BeingFacet.objects.create(being=self.being, facet=scythe)


class BeingNicknameTests(TestCase):
    def test_being_can_have_multiple_nicknames(self) -> None:
        being = WorshippedBeingFactory()
        BeingNickname.objects.create(being=being, name="the Crimson")
        BeingNickname.objects.create(being=being, name="Old Resting Murder Face")
        self.assertEqual(being.nicknames.count(), 2)


class BeingResonanceTests(TestCase):
    def test_being_can_hold_favored_and_associated_resonances(self) -> None:
        being = WorshippedBeingFactory()
        savagery = ResonanceFactory(name="Savagery")
        wrath = ResonanceFactory(name="Wrath")
        BeingResonance.objects.create(
            being=being, resonance=savagery, tier=BeingResonanceTier.FAVORED
        )
        BeingResonance.objects.create(
            being=being, resonance=wrath, tier=BeingResonanceTier.ASSOCIATED
        )
        self.assertEqual(being.resonances.count(), 2)
        self.assertEqual(being.resonances.get(resonance=savagery).tier, BeingResonanceTier.FAVORED)

    def test_unique_per_being_and_resonance(self) -> None:
        being = WorshippedBeingFactory()
        savagery = ResonanceFactory(name="Savagery")
        BeingResonance.objects.create(
            being=being, resonance=savagery, tier=BeingResonanceTier.FAVORED
        )
        with transaction.atomic(), self.assertRaises(IntegrityError):
            BeingResonance.objects.create(
                being=being, resonance=savagery, tier=BeingResonanceTier.ASSOCIATED
            )
