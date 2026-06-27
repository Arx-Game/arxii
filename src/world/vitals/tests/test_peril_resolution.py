"""Tests for world.vitals.peril_resolution (Task 3 of #1479).

Covers:
- is_pc_source: None → False; NPC character → False; PC character → True.
- death_is_permitted:
  (a) PC source → False (ADR-0023: PvP is structurally non-lethal).
  (b) NPC source, no death_deferred → True.
  (c) NPC source, victim has active death_deferred condition → False.
  (d) None source → False (absent/non-lethal context).

SQLite-compatible: ConditionInstances are created directly (not via
apply_condition, which relies on a PG-only DISTINCT ON path).
"""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.mechanics.factories import DeathDeferredPropertyFactory


def _make_pc_character():
    """Return a character backed by an AccountDB (player-controlled)."""
    account = AccountFactory()
    character = CharacterFactory()
    character.db_account = account
    character.save(update_fields=["db_account"])
    return character


def _make_npc_character():
    """Return a character with no linked account (NPC)."""
    return CharacterFactory()


def _make_sheet_with_death_deferred():
    """Return a (sheet, character) where the character has an active death_deferred condition."""
    sheet = CharacterSheetFactory()
    character = sheet.character
    prop = DeathDeferredPropertyFactory()
    template = ConditionTemplateFactory()
    template.properties.add(prop)
    ConditionInstanceFactory(target=character, condition=template)
    return sheet, character


class IsPcSourceTests(TestCase):
    """Unit tests for is_pc_source()."""

    def test_none_source_returns_false(self) -> None:
        from world.vitals.peril_resolution import is_pc_source

        self.assertFalse(is_pc_source(None))

    def test_npc_character_returns_false(self) -> None:
        from world.vitals.peril_resolution import is_pc_source

        npc = _make_npc_character()
        self.assertFalse(is_pc_source(npc))

    def test_pc_character_returns_true(self) -> None:
        from world.vitals.peril_resolution import is_pc_source

        pc = _make_pc_character()
        self.assertTrue(is_pc_source(pc))


class DeathIsPermittedTests(TestCase):
    """Unit tests for death_is_permitted()."""

    def setUp(self) -> None:
        self.victim_sheet = CharacterSheetFactory()

    def test_pc_source_returns_false(self) -> None:
        """ADR-0023: PvP is structurally non-lethal — death never permitted from a PC."""
        from world.vitals.peril_resolution import death_is_permitted

        pc = _make_pc_character()
        self.assertFalse(death_is_permitted(victim_sheet=self.victim_sheet, source_character=pc))

    def test_npc_source_no_flags_returns_true(self) -> None:
        """A significant-NPC source with no death_deferred condition → death permitted."""
        from world.vitals.peril_resolution import death_is_permitted

        npc = _make_npc_character()
        self.assertTrue(death_is_permitted(victim_sheet=self.victim_sheet, source_character=npc))

    def test_npc_source_death_deferred_returns_false(self) -> None:
        """Victim carrying an active death_deferred condition blocks death even from an NPC."""
        from world.vitals.peril_resolution import death_is_permitted

        victim_sheet, _char = _make_sheet_with_death_deferred()
        npc = _make_npc_character()
        self.assertFalse(death_is_permitted(victim_sheet=victim_sheet, source_character=npc))

    def test_none_source_returns_false(self) -> None:
        """Absent/environmental source is non-lethal by default."""
        from world.vitals.peril_resolution import death_is_permitted

        self.assertFalse(death_is_permitted(victim_sheet=self.victim_sheet, source_character=None))
