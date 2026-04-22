"""Tests for CharacterThreadHandler and CharacterResonanceHandler (Spec A §3.7)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    CharacterResonanceFactory,
    ResonanceFactory,
    ThreadFactory,
)


class CharacterThreadHandlerTests(TestCase):
    def test_all_returns_owned_threads_only(self) -> None:
        sheet = CharacterSheetFactory()
        ThreadFactory(owner=sheet)
        ThreadFactory(owner=sheet)
        ThreadFactory()  # different owner

        threads = sheet.character.threads.all()
        self.assertEqual(len(threads), 2)
        self.assertTrue(all(t.owner_id == sheet.pk for t in threads))

    def test_all_caches_after_first_read(self) -> None:
        sheet = CharacterSheetFactory()
        ThreadFactory(owner=sheet)
        # Warm cache.
        sheet.character.threads.all()
        with self.assertNumQueries(0):
            sheet.character.threads.all()

    def test_invalidate_clears_cache(self) -> None:
        sheet = CharacterSheetFactory()
        ThreadFactory(owner=sheet)
        # Warm cache.
        sheet.character.threads.all()
        sheet.character.threads.invalidate()
        with self.assertNumQueries(1):
            sheet.character.threads.all()

    def test_by_resonance_filters_to_one_resonance(self) -> None:
        sheet = CharacterSheetFactory()
        res_a = ResonanceFactory()
        res_b = ResonanceFactory()
        ThreadFactory(owner=sheet, resonance=res_a)
        ThreadFactory(owner=sheet, resonance=res_a)
        ThreadFactory(owner=sheet, resonance=res_b)

        a_threads = sheet.character.threads.by_resonance(res_a)
        b_threads = sheet.character.threads.by_resonance(res_b)
        self.assertEqual(len(a_threads), 2)
        self.assertEqual(len(b_threads), 1)


class CharacterResonanceHandlerTests(TestCase):
    def test_balance_returns_zero_for_unknown_resonance(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        self.assertEqual(sheet.character.resonances.balance(res), 0)

    def test_balance_and_lifetime_read_existing_row(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=sheet,
            resonance=res,
            balance=4,
            lifetime_earned=9,
        )
        self.assertEqual(sheet.character.resonances.balance(res), 4)
        self.assertEqual(sheet.character.resonances.lifetime(res), 9)

    def test_get_or_create_creates_lazy_row(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        cr = sheet.character.resonances.get_or_create(res)
        self.assertEqual(cr.balance, 0)
        self.assertEqual(cr.lifetime_earned, 0)
        # Cached after creation.
        again = sheet.character.resonances.get_or_create(res)
        self.assertEqual(again.pk, cr.pk)

    def test_most_recently_earned_returns_max_lifetime(self) -> None:
        sheet = CharacterSheetFactory()
        res_a = ResonanceFactory()
        res_b = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=sheet,
            resonance=res_a,
            lifetime_earned=10,
        )
        winner = CharacterResonanceFactory(
            character_sheet=sheet,
            resonance=res_b,
            lifetime_earned=20,
        )
        self.assertEqual(
            sheet.character.resonances.most_recently_earned().pk,
            winner.pk,
        )

    def test_most_recently_earned_returns_none_when_empty(self) -> None:
        sheet = CharacterSheetFactory()
        self.assertIsNone(sheet.character.resonances.most_recently_earned())

    def test_invalidate_clears_cache(self) -> None:
        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=sheet, resonance=res)
        # Warm cache.
        sheet.character.resonances.all()
        sheet.character.resonances.invalidate()
        with self.assertNumQueries(1):
            sheet.character.resonances.all()
