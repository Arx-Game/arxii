"""Tests for the Mission ITEM reward sink (#707)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemTemplateFactory
from world.items.models import ItemInstance
from world.missions.constants import DeedRewardKind, DeedRewardSink
from world.missions.factories import MissionDeedRecordFactory, MissionDeedRewardLineFactory
from world.missions.services.rewards import _route_line


class ItemRewardSinkTests(TestCase):
    def test_immediate_item_line_grants_the_item(self) -> None:
        # A plain CharacterFactory() has no CharacterSheet (sheet_data raises
        # RelatedObjectDoesNotExist) — the ITEM branch requires a real sheet
        # (unlike MONEY, which falls back to a stub for sheet-less
        # recipients), so the recipient needs a CharacterSheetFactory-backed
        # character.
        recipient = CharacterSheetFactory().character
        template = ItemTemplateFactory()
        deed = MissionDeedRecordFactory()
        line = MissionDeedRewardLineFactory(
            deed=deed,
            recipient=recipient,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.ITEM,
            item_template=template,
        )
        enqueued: list = []
        stub_calls: list = []
        _route_line(deed, line, enqueued, stub_calls)
        assert ItemInstance.objects.filter(
            template=template, holder_character_sheet=recipient.sheet_data
        ).exists()
        assert enqueued == []
