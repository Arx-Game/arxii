"""Tests for CharacterCompanionHandler (#672)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.companions.factories import CompanionFactory
from world.companions.handlers import CharacterCompanionHandler


class CharacterCompanionHandlerTests(TestCase):
    def test_active_returns_only_unreleased_companions(self) -> None:
        from django.utils import timezone

        sheet = CharacterSheetFactory()
        active_companion = CompanionFactory(owner=sheet)
        released_companion = CompanionFactory(owner=sheet)
        released_companion.released_at = timezone.now()
        released_companion.save(update_fields=["released_at"])

        handler = CharacterCompanionHandler(sheet.character)

        result = handler.active()

        self.assertIn(active_companion, result)
        self.assertNotIn(released_companion, result)

    def test_active_returns_empty_list_without_sheet(self) -> None:
        from evennia_extensions.factories import ObjectDBFactory

        sheetless = ObjectDBFactory()
        handler = CharacterCompanionHandler(sheetless)

        self.assertEqual(handler.active(), [])

    def test_find_walks_the_cached_list_without_a_query(self) -> None:
        sheet = CharacterSheetFactory()
        grey = CompanionFactory(owner=sheet, name="Old Grey")
        handler = CharacterCompanionHandler(sheet.character)
        handler.active()

        with self.assertNumQueries(0):
            self.assertEqual(handler.find("old grey"), grey)
            self.assertEqual(handler.find(str(grey.pk)), grey)
            self.assertIsNone(handler.find("Old"))
            self.assertIsNone(handler.find(str(grey.pk + 1000)))

    def test_invalidate_reloads_after_a_row_lands_outside_the_handler(self) -> None:
        sheet = CharacterSheetFactory()
        handler = CharacterCompanionHandler(sheet.character)
        self.assertEqual(handler.active(), [])

        skree = CompanionFactory(owner=sheet, name="Skree")

        self.assertIsNone(handler.find("Skree"))
        handler.invalidate()
        self.assertEqual(handler.find("Skree"), skree)
