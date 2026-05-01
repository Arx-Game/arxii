"""Tests for the multi-layer identity guards used by CombatOpponent."""

from evennia import create_object
from evennia.utils.test_resources import EvenniaTestCase


class IsCombatNPCTypeclassTests(EvenniaTestCase):
    def test_returns_true_for_combat_npc(self):
        from world.combat.services import is_combat_npc_typeclass
        from world.combat.typeclasses.combat_npc import CombatNPC

        npc = create_object(CombatNPC, key="Mook")
        self.assertTrue(is_combat_npc_typeclass(npc))

    def test_returns_false_for_plain_character(self):
        from world.combat.services import is_combat_npc_typeclass

        char = create_object("typeclasses.characters.Character", key="PC")
        self.assertFalse(is_combat_npc_typeclass(char))


class HasPersistentIdentityReferencesTests(EvenniaTestCase):
    def test_detects_character_sheet(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.services import has_persistent_identity_references

        sheet = CharacterSheetFactory()
        self.assertTrue(has_persistent_identity_references(sheet.character))

    def test_returns_false_for_combat_npc(self):
        from world.combat.services import has_persistent_identity_references
        from world.combat.typeclasses.combat_npc import CombatNPC

        npc = create_object(CombatNPC, key="Mook")
        self.assertFalse(has_persistent_identity_references(npc))
