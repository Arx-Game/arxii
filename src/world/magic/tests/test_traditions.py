from django.test import TestCase

from world.magic.factories import (
    AffinityFactory,
    CharacterTraditionFactory,
    GiftFactory,
    ResonanceFactory,
    TraditionFactory,
)
from world.magic.models import CharacterTradition, Gift, Tradition


class TraditionModelTests(TestCase):
    """Tests for the Tradition model."""

    def test_create_tradition(self):
        tradition = TraditionFactory()
        assert Tradition.objects.filter(pk=tradition.pk).exists()
        assert str(tradition) == tradition.name

    def test_tradition_ordering(self):
        t2 = TraditionFactory(sort_order=2, name="Bravo")
        t1 = TraditionFactory(sort_order=1, name="Alpha")
        t3 = TraditionFactory(sort_order=1, name="Charlie")
        result = list(Tradition.objects.all())
        assert result == [t1, t3, t2]


class CharacterTraditionTests(TestCase):
    """Tests for CharacterTradition -- one ACTIVE row per character, history preserved.

    #2441 Task 8 ratified "every character has exactly one tradition at a time"
    (#2426) as a DB constraint (`unique_active_tradition_per_character`, `character`
    WHERE `left_at IS NULL`) and dropped the old `unique_together` on
    (character, tradition) — a character may rejoin a tradition they previously
    left, which needs a second historical row for the same pair.
    """

    def test_create_character_tradition(self):
        ct = CharacterTraditionFactory()
        assert CharacterTradition.objects.filter(pk=ct.pk).exists()

    def test_second_active_tradition_conflicts(self):
        from django.db import IntegrityError

        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        t1 = TraditionFactory(name="Tradition A")
        t2 = TraditionFactory(name="Tradition B")
        CharacterTradition.objects.create(character=sheet, tradition=t1)
        with self.assertRaises(IntegrityError):
            CharacterTradition.objects.create(character=sheet, tradition=t2)

    def test_historical_rows_allowed_after_leaving(self):
        from django.utils import timezone

        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        t1 = TraditionFactory(name="Tradition A")
        t2 = TraditionFactory(name="Tradition B")
        old = CharacterTradition.objects.create(character=sheet, tradition=t1)
        old.left_at = timezone.now()
        old.save(update_fields=["left_at"])
        CharacterTradition.objects.create(character=sheet, tradition=t2)
        assert sheet.character_traditions.count() == 2

    def test_unique_together_dropped_rejoin_allowed(self):
        """Rejoining a previously-left tradition creates a second historical row."""
        from django.utils import timezone

        ct = CharacterTraditionFactory()
        ct.left_at = timezone.now()
        ct.save(update_fields=["left_at"])
        rejoined = CharacterTradition.objects.create(character=ct.character, tradition=ct.tradition)
        active_count = ct.character.character_traditions.filter(left_at__isnull=True).count()
        assert active_count == 1
        assert rejoined.pk != ct.pk


class GiftDerivedAffinityTests(TestCase):
    """Tests for derived affinity on Gift."""

    @classmethod
    def setUpTestData(cls):
        cls.celestial_affinity = AffinityFactory(name="Celestial")
        cls.abyssal_affinity = AffinityFactory(name="Abyssal")
        cls.celestial_res = ResonanceFactory(name="Bene", affinity=cls.celestial_affinity)
        cls.abyssal_res = ResonanceFactory(name="Insidia", affinity=cls.abyssal_affinity)

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
