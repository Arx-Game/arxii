"""Tests for grant_touchstone_item_to_character (#707)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemTemplateFactory
from world.items.models import ItemInstance
from world.items.services.narrative_grants import grant_touchstone_item_to_character


class GrantTouchstoneItemToCharacterTests(TestCase):
    def test_creates_instance_held_by_character(self) -> None:
        sheet = CharacterSheetFactory()
        template = ItemTemplateFactory()
        instance = grant_touchstone_item_to_character(character_sheet=sheet, template=template)
        assert isinstance(instance, ItemInstance)
        assert instance.template_id == template.pk
        assert instance.holder_character_sheet_id == sheet.pk

    def test_granted_by_is_not_required(self) -> None:
        sheet = CharacterSheetFactory()
        template = ItemTemplateFactory()
        instance = grant_touchstone_item_to_character(character_sheet=sheet, template=template)
        assert instance.pk is not None

    def test_granted_by_is_recorded_for_audit_only(self) -> None:
        sheet = CharacterSheetFactory()
        template = ItemTemplateFactory()
        account = AccountFactory()
        instance = grant_touchstone_item_to_character(
            character_sheet=sheet, template=template, granted_by=account
        )
        assert instance.holder_character_sheet_id == sheet.pk
