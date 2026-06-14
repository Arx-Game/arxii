"""Tests for mantle clearance services + the character handler (#512)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CharacterCodexKnowledgeFactory, CodexEntryFactory
from world.items.factories import MantleFactory, MantleLevelDefinitionFactory
from world.items.models import MantleLevelClearance
from world.items.services.mantle import (
    get_max_cleared_mantle_level,
    grant_mantle_clearance,
    record_mantle_clearances,
)
from world.roster.factories import RosterEntryFactory


def _learn(roster_entry, entry):
    """Create a fully-learned (KNOWN) CharacterCodexKnowledge row."""
    return CharacterCodexKnowledgeFactory(
        roster_entry=roster_entry,
        entry=entry,
        status=CodexKnowledgeStatus.KNOWN,
    )


class MantleClearanceServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet=cls.sheet)
        cls.mantle = MantleFactory()
        cls.entry_l1 = CodexEntryFactory(name="Mantle Lore I")
        cls.entry_l2 = CodexEntryFactory(name="Mantle Lore II")
        cls.def_l1 = MantleLevelDefinitionFactory(
            mantle=cls.mantle, level=1, codex_entry_required=cls.entry_l1
        )
        cls.def_l2 = MantleLevelDefinitionFactory(
            mantle=cls.mantle, level=2, codex_entry_required=cls.entry_l2
        )

    def test_no_codex_knowledge_records_nothing(self) -> None:
        created = record_mantle_clearances(self.sheet, self.mantle)
        self.assertEqual(created, [])
        self.assertEqual(get_max_cleared_mantle_level(self.sheet, self.mantle), 0)

    def test_level_one_learned_records_level_one_only(self) -> None:
        _learn(self.roster_entry, self.entry_l1)

        created = record_mantle_clearances(self.sheet, self.mantle)

        self.assertEqual([c.level for c in created], [1])
        self.assertEqual(get_max_cleared_mantle_level(self.sheet, self.mantle), 1)

    def test_in_order_gate_stops_at_first_unmet_level(self) -> None:
        # Level 2's entry is learned but level 1's is NOT — the in-order gate
        # must stop at level 1, recording nothing.
        _learn(self.roster_entry, self.entry_l2)

        created = record_mantle_clearances(self.sheet, self.mantle)

        self.assertEqual(created, [])
        self.assertEqual(get_max_cleared_mantle_level(self.sheet, self.mantle), 0)

    def test_both_levels_learned_records_both(self) -> None:
        _learn(self.roster_entry, self.entry_l1)
        _learn(self.roster_entry, self.entry_l2)

        created = record_mantle_clearances(self.sheet, self.mantle)

        self.assertEqual({c.level for c in created}, {1, 2})
        self.assertEqual(get_max_cleared_mantle_level(self.sheet, self.mantle), 2)

    def test_record_is_idempotent(self) -> None:
        _learn(self.roster_entry, self.entry_l1)

        first = record_mantle_clearances(self.sheet, self.mantle)
        second = record_mantle_clearances(self.sheet, self.mantle)

        self.assertEqual([c.level for c in first], [1])
        self.assertEqual(second, [])  # nothing new
        self.assertEqual(
            MantleLevelClearance.objects.filter(
                character_sheet=self.sheet, mantle=self.mantle
            ).count(),
            1,
        )

    def test_unlearned_codex_status_does_not_clear(self) -> None:
        # UNCOVERED (in-progress) knowledge must NOT count as learned.
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.entry_l1,
            status=CodexKnowledgeStatus.UNCOVERED,
        )

        created = record_mantle_clearances(self.sheet, self.mantle)

        self.assertEqual(created, [])
        self.assertEqual(get_max_cleared_mantle_level(self.sheet, self.mantle), 0)

    def test_grant_bypasses_codex_check(self) -> None:
        clearance = grant_mantle_clearance(self.sheet, self.mantle, level=2)

        self.assertEqual(clearance.level, 2)
        self.assertEqual(get_max_cleared_mantle_level(self.sheet, self.mantle), 2)

    def test_grant_is_idempotent(self) -> None:
        first = grant_mantle_clearance(self.sheet, self.mantle, level=1)
        second = grant_mantle_clearance(self.sheet, self.mantle, level=1)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            MantleLevelClearance.objects.filter(
                character_sheet=self.sheet, mantle=self.mantle
            ).count(),
            1,
        )


class CharacterMantleClearanceHandlerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.roster_entry = RosterEntryFactory(character_sheet=cls.sheet)
        cls.mantle = MantleFactory()
        cls.entry_l1 = CodexEntryFactory(name="Handler Lore I")
        cls.def_l1 = MantleLevelDefinitionFactory(
            mantle=cls.mantle, level=1, codex_entry_required=cls.entry_l1
        )
        _learn(cls.roster_entry, cls.entry_l1)

    def test_handler_reflects_recorded_clearances(self) -> None:
        self.assertEqual(self.character.mantle_clearances.max_cleared_level(self.mantle), 0)

        record_mantle_clearances(self.sheet, self.mantle)
        self.character.mantle_clearances.invalidate()

        self.assertEqual(self.character.mantle_clearances.max_cleared_level(self.mantle), 1)

    def test_handler_zero_for_uncleared_mantle(self) -> None:
        other_mantle = MantleFactory()
        self.assertEqual(
            self.character.mantle_clearances.max_cleared_level(other_mantle), 0
        )
