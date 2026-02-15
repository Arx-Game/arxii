from django.test import TestCase

from world.magic.factories import (
    CharacterTraditionFactory,
    GiftFactory,
    ResonanceModifierTypeFactory,
    TraditionFactory,
)
from world.magic.models import CharacterTradition, Gift, Tradition
from world.mechanics.factories import ModifierCategoryFactory, ModifierTypeFactory


class TraditionModelTests(TestCase):
    """Tests for the Tradition model."""

    def test_create_tradition(self):
        tradition = TraditionFactory()
        assert Tradition.objects.filter(pk=tradition.pk).exists()
        assert str(tradition) == tradition.name

    def test_tradition_with_society(self):
        from world.societies.factories import SocietyFactory

        society = SocietyFactory()
        tradition = TraditionFactory(society=society)
        assert tradition.society == society

    def test_tradition_ordering(self):
        t2 = TraditionFactory(sort_order=2, name="Bravo")
        t1 = TraditionFactory(sort_order=1, name="Alpha")
        t3 = TraditionFactory(sort_order=1, name="Charlie")
        result = list(Tradition.objects.all())
        assert result == [t1, t3, t2]


class CharacterTraditionTests(TestCase):
    """Tests for CharacterTradition -- multiple per character."""

    def test_create_character_tradition(self):
        ct = CharacterTraditionFactory()
        assert CharacterTradition.objects.filter(pk=ct.pk).exists()

    def test_multiple_traditions_per_character(self):
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        t1 = TraditionFactory(name="Tradition A")
        t2 = TraditionFactory(name="Tradition B")
        CharacterTradition.objects.create(character=sheet, tradition=t1)
        CharacterTradition.objects.create(character=sheet, tradition=t2)
        assert sheet.character_traditions.count() == 2

    def test_unique_together(self):
        from django.db import IntegrityError

        ct = CharacterTraditionFactory()
        with self.assertRaises(IntegrityError):
            CharacterTradition.objects.create(character=ct.character, tradition=ct.tradition)


class GiftDerivedAffinityTests(TestCase):
    """Tests for derived affinity on Gift."""

    @classmethod
    def setUpTestData(cls):
        cls.celestial_affinity = ModifierTypeFactory(
            name="Celestial",
            category=ModifierCategoryFactory(name="affinity"),
        )
        cls.abyssal_affinity = ModifierTypeFactory(
            name="Abyssal",
            category=ModifierCategoryFactory(name="affinity"),
        )
        cls.celestial_res = ResonanceModifierTypeFactory(
            name="Bene", affiliated_affinity=cls.celestial_affinity
        )
        cls.abyssal_res = ResonanceModifierTypeFactory(
            name="Insidia", affiliated_affinity=cls.abyssal_affinity
        )

    def test_no_resonances_returns_empty(self):
        gift = GiftFactory()
        assert gift.get_affinity_breakdown() == {}

    def test_single_resonance_affinity(self):
        gift = GiftFactory()
        gift.resonances.add(self.celestial_res)
        breakdown = gift.get_affinity_breakdown()
        assert breakdown == {"Celestial": 1}

    def test_mixed_resonances(self):
        gift = GiftFactory()
        gift.resonances.add(self.celestial_res, self.abyssal_res)
        breakdown = gift.get_affinity_breakdown()
        assert breakdown == {"Celestial": 1, "Abyssal": 1}

    def test_gift_creates_without_affinity(self):
        """Gift can be created without specifying affinity."""
        gift = Gift.objects.create(name="Test Gift")
        assert gift.pk is not None
