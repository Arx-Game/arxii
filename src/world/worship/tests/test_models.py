"""Model tests for the worship foundation (#2355)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import ResonanceFactory
from world.magic.models import Facet
from world.tarot.factories import TarotCardFactory
from world.worship.constants import BeingRelationshipValence, BeingResonanceTier
from world.worship.factories import (
    BeingRelationshipFactory,
    DevotionStandingFactory,
    WorshipDeclarationFactory,
    WorshippedBeingFactory,
    WorshipTraditionFactory,
)
from world.worship.models import (
    BeingFacet,
    BeingNickname,
    BeingRelationship,
    BeingResonance,
    WorshipFeastDay,
)


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


class WorshippedBeingDomainsTests(TestCase):
    def test_domains_is_freeform_text(self) -> None:
        being = WorshippedBeingFactory(domains="Carnage, wanton bloodshed, feral battle, ferocity")
        self.assertIn("Carnage", being.domains)

    def test_domains_defaults_blank(self) -> None:
        being = WorshippedBeingFactory()
        self.assertEqual(being.domains, "")


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


class BeingRelationshipTests(TestCase):
    def test_relationship_has_only_public_story(self) -> None:
        fleshreaper = WorshippedBeingFactory(name="Fleshreaper")
        leviathan = WorshippedBeingFactory(name="Leviathan")
        rel = BeingRelationship.objects.create(
            being_a=fleshreaper,
            being_b=leviathan,
            valence=BeingRelationshipValence.ALLY,
            public_story="Old friends since before the Godswar.",
        )
        self.assertEqual(rel.public_story, "Old friends since before the Godswar.")
        self.assertFalse(hasattr(rel, "hidden_truth"))

    def test_no_self_relationship(self) -> None:
        being = WorshippedBeingFactory()
        with transaction.atomic(), self.assertRaises(IntegrityError):
            BeingRelationship.objects.create(
                being_a=being, being_b=being, valence=BeingRelationshipValence.ALLY
            )

    def test_normalizes_reversed_args_to_canonical_pk_order(self) -> None:
        """ALLY/RIVAL/FEUD/UNKNOWN are undirected facts — being_a/being_b carry no
        meaning of their own, so ``save()`` sorts them into pk-ascending order
        regardless of which order a caller passes them in (#3776 Task 8
        investigation: closes the reverse-pair duplicate gap — see
        ``test_reversed_duplicate_conflicts_with_existing_pair``)."""
        first = WorshippedBeingFactory()
        second = WorshippedBeingFactory()
        self.assertLess(first.pk, second.pk)
        rel = BeingRelationship.objects.create(
            being_a=second, being_b=first, valence=BeingRelationshipValence.FEUD
        )
        self.assertEqual(rel.being_a_id, first.pk)
        self.assertEqual(rel.being_b_id, second.pk)

    def test_reversed_duplicate_conflicts_with_existing_pair(self) -> None:
        """Without normalization, recording (a, b) and then (b, a) would satisfy
        ``unique_being_relationship_pair`` twice over and produce two rows for the
        same undirected fact. Normalization collapses both onto one row, so the
        second attempt collides with the first instead of duplicating it."""
        fleshreaper = WorshippedBeingFactory(name="Fleshreaper Duplicate Check")
        leviathan = WorshippedBeingFactory(name="Leviathan Duplicate Check")
        BeingRelationshipFactory(
            being_a=fleshreaper, being_b=leviathan, valence=BeingRelationshipValence.RIVAL
        )
        with transaction.atomic(), self.assertRaises(IntegrityError):
            BeingRelationship.objects.create(
                being_a=leviathan, being_b=fleshreaper, valence=BeingRelationshipValence.RIVAL
            )


class WorshipFeastDayTests(TestCase):
    def test_feast_day_recurs_by_month_and_day_no_year(self) -> None:
        being = WorshippedBeingFactory()
        feast = WorshipFeastDay.objects.create(
            being=being, ic_month=9, ic_day=14, name="The Long Bleeding"
        )
        self.assertFalse(hasattr(feast, "year"))

    def test_unique_per_being_and_date(self) -> None:
        being = WorshippedBeingFactory()
        WorshipFeastDay.objects.create(being=being, ic_month=9, ic_day=14, name="A")
        with transaction.atomic(), self.assertRaises(IntegrityError):
            WorshipFeastDay.objects.create(being=being, ic_month=9, ic_day=14, name="B")


class WorshippedBeingTarotTests(TestCase):
    def test_being_can_hold_multiple_tarot_cards(self) -> None:
        being = WorshippedBeingFactory()
        tower = TarotCardFactory(name="The Tower")
        being.tarot_cards.add(tower)
        self.assertEqual(being.tarot_cards.count(), 1)
