"""ThreadResonance rows and the leading resonance (#5123)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadResonanceFactory,
)
from world.magic.models import Thread, ThreadResonance
from world.magic.services.thread_rows import refresh_leading_resonance


class LeadingResonanceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.fury = ResonanceFactory(name="Fury")
        cls.domination = ResonanceFactory(name="Domination")
        cls.wonder = ResonanceFactory(name="Wonder")

    def test_leading_is_largest_amount(self) -> None:
        thread = ThreadFactory(resonance=self.fury, developed_points=10)
        ThreadResonanceFactory(thread=thread, resonance=self.domination, amount=15)

        leading = refresh_leading_resonance(thread)

        self.assertEqual(leading, self.domination)
        thread.refresh_from_db()
        self.assertEqual(thread.resonance, self.domination)

    def test_tie_goes_to_first_created(self) -> None:
        thread = ThreadFactory(resonance=self.fury, developed_points=5)
        ThreadResonanceFactory(thread=thread, resonance=self.domination, amount=5)
        ThreadResonanceFactory(thread=thread, resonance=self.wonder, amount=5)

        self.assertEqual(refresh_leading_resonance(thread), self.fury)

    def test_unchanged_leader_does_not_write(self) -> None:
        thread = ThreadFactory(resonance=self.fury, developed_points=10)
        ThreadResonanceFactory(thread=thread, resonance=self.domination, amount=3)

        with self.assertNumQueries(1):
            refresh_leading_resonance(thread)

    def test_refresh_without_rows_raises(self) -> None:
        thread = ThreadFactory(resonance=self.fury)
        ThreadResonance.objects.filter(thread=thread).delete()

        with self.assertRaises(ValueError):
            refresh_leading_resonance(thread)

    def test_factory_row_matches_the_thread(self) -> None:
        thread = ThreadFactory(resonance=self.fury, developed_points=7)

        rows = list(thread.resonance_rows.all())

        self.assertEqual([(r.resonance, r.amount) for r in rows], [(self.fury, 7)])


class OneThreadPerAnchorTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()

    def test_one_thread_per_anchor_constraint(self) -> None:
        ThreadFactory(
            owner=self.sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            target_trait=None,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Thread.objects.create(
                owner=self.sheet,
                resonance=ResonanceFactory(),
                target_kind=TargetKind.GIFT,
                target_gift=self.gift,
            )
