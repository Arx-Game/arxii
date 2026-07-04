"""Tests for ItemInstance attunement fields (#707)."""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemInstanceFactory
from world.items.models import ItemInstance


class ItemInstanceAttunementTests(TestCase):
    def test_default_instance_is_unattuned(self) -> None:
        instance = ItemInstanceFactory()
        assert instance.attuned_to_character_sheet_id is None
        assert instance.attuned_at is None

    def test_can_mark_instance_attuned(self) -> None:
        sheet = CharacterSheetFactory()
        instance = ItemInstanceFactory()
        now = timezone.now()
        instance.attuned_to_character_sheet = sheet
        instance.attuned_at = now
        instance.save()
        instance.refresh_from_db()
        assert instance.attuned_to_character_sheet_id == sheet.pk
        assert instance.attuned_at == now

    def test_deleting_character_sheet_nulls_attunement(self) -> None:
        sheet = CharacterSheetFactory()
        instance = ItemInstanceFactory(attuned_to_character_sheet=sheet, attuned_at=timezone.now())
        sheet.delete()
        # The Collector-driven SET_NULL is a bulk `.update()` on the FK
        # target's delete() — it bypasses per-instance `.save()`, so the
        # idmapper identity map keeps serving the stale cached instance even
        # after `refresh_from_db()` (see sharedmemory-model skill's
        # "Known stale-cache traps", case 2). Flush before re-reading.
        ItemInstance.flush_instance_cache()
        instance.refresh_from_db()
        assert instance.attuned_to_character_sheet_id is None
