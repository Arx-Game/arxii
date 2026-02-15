from django.test import TestCase

from world.magic.factories import CharacterTraditionFactory, TraditionFactory
from world.magic.models import CharacterTradition, Tradition


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
