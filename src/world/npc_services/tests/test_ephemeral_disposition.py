"""Tests for the ephemeral disposition store for persona-less NPCs."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.npc_services.ephemeral_disposition import (
    adjust_disposition,
    clear_for_pair,
    clear_scene_disposition,
    get_disposition,
)


class EphemeralDispositionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pc_sheet = CharacterSheetFactory()
        cls.other_pc = CharacterSheetFactory()
        cls.npc_character = CharacterFactory()
        cls.other_npc_character = CharacterFactory()

    def test_default_zero(self):
        store = {}
        self.assertEqual(get_disposition(store, self.pc_sheet, self.npc_character), 0)

    def test_adjust_accumulates(self):
        store = {}
        adjust_disposition(store, self.pc_sheet, self.npc_character, delta=5)
        adjust_disposition(store, self.pc_sheet, self.npc_character, delta=3)
        self.assertEqual(get_disposition(store, self.pc_sheet, self.npc_character), 8)

    def test_isolated_per_pc_and_npc(self):
        store = {}
        adjust_disposition(store, self.pc_sheet, self.npc_character, delta=5)
        # Different PC, same NPC:
        self.assertEqual(get_disposition(store, self.other_pc, self.npc_character), 0)

    def test_clear_scene_removes_only_that_pc(self):
        store = {}
        adjust_disposition(store, self.pc_sheet, self.npc_character, delta=5)
        adjust_disposition(store, self.other_pc, self.npc_character, delta=9)
        clear_scene_disposition(store, self.pc_sheet)
        self.assertEqual(get_disposition(store, self.pc_sheet, self.npc_character), 0)
        self.assertEqual(get_disposition(store, self.other_pc, self.npc_character), 9)

    def test_clear_for_pair_removes_only_one_npc(self):
        store = {}
        adjust_disposition(store, self.pc_sheet, self.npc_character, delta=5)
        adjust_disposition(store, self.pc_sheet, self.other_npc_character, delta=7)
        clear_for_pair(store, self.pc_sheet, self.npc_character)
        self.assertEqual(get_disposition(store, self.pc_sheet, self.npc_character), 0)
        self.assertEqual(get_disposition(store, self.pc_sheet, self.other_npc_character), 7)
