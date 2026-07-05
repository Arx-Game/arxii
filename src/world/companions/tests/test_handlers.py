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
