"""A grant reaches the characters already in its group (#3775)."""

from django.test import TestCase
from django.utils import timezone

from world.character_creation.factories import BeginningsFactory
from world.character_sheets.factories import ProfileBeginningsFactory
from world.classes.factories import PathFactory
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CodexEntryFactory
from world.codex.models import (
    BeginningsCodexGrant,
    CharacterCodexKnowledge,
    DistinctionCodexGrant,
    PathCodexGrant,
    TraditionCodexGrant,
)
from world.codex.services import grant_to_current_holders
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.magic.factories import CharacterTraditionFactory, TraditionFactory
from world.progression.factories import CharacterPathHistoryFactory
from world.roster.factories import RosterEntryFactory


def _known(roster_entry, entry) -> bool:
    return CharacterCodexKnowledge.objects.filter(
        roster_entry=roster_entry, entry=entry, status=CodexKnowledgeStatus.KNOWN
    ).exists()


class BeginningsHoldersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.entry = CodexEntryFactory(name="The Five Castes")
        cls.beginnings = BeginningsFactory(name="The Blessed")
        cls.holder = RosterEntryFactory()
        ProfileBeginningsFactory(
            profile=cls.holder.character_sheet.true_profile, beginnings=cls.beginnings
        )
        cls.stranger = RosterEntryFactory()
        cls.grant = BeginningsCodexGrant.objects.create(beginnings=cls.beginnings, entry=cls.entry)

    def test_holder_learns_and_stranger_does_not(self):
        learned = grant_to_current_holders(self.grant)

        self.assertEqual(learned, 1)
        self.assertTrue(_known(self.holder, self.entry))
        self.assertFalse(_known(self.stranger, self.entry))

    def test_repeat_is_a_noop(self):
        grant_to_current_holders(self.grant)
        self.assertEqual(grant_to_current_holders(self.grant), 0)

    def test_a_character_with_two_origins_holds_both(self):
        other = BeginningsFactory(name="Twilight Court")
        ProfileBeginningsFactory(
            profile=self.holder.character_sheet.true_profile,
            beginnings=other,
            source="recovered_memory",
        )
        other_entry = CodexEntryFactory(name="The Twilight Court")
        other_grant = BeginningsCodexGrant.objects.create(beginnings=other, entry=other_entry)

        grant_to_current_holders(self.grant)
        grant_to_current_holders(other_grant)

        self.assertTrue(_known(self.holder, self.entry))
        self.assertTrue(_known(self.holder, other_entry))


class TraditionHoldersTests(TestCase):
    def test_active_member_learns_former_member_does_not(self):
        entry = CodexEntryFactory(name="The Sanguinus")
        tradition = TraditionFactory(name="Sanguinus")
        active = RosterEntryFactory()
        former = RosterEntryFactory()
        CharacterTraditionFactory(character=active.character_sheet, tradition=tradition)
        CharacterTraditionFactory(
            character=former.character_sheet, tradition=tradition, left_at=timezone.now()
        )
        grant = TraditionCodexGrant.objects.create(tradition=tradition, entry=entry)

        self.assertEqual(grant_to_current_holders(grant), 1)
        self.assertTrue(_known(active, entry))
        self.assertFalse(_known(former, entry))


class PathHoldersTests(TestCase):
    def test_any_history_row_counts(self):
        entry = CodexEntryFactory(name="The Path of Steel")
        path = PathFactory(name="Path of Steel")
        later = PathFactory(name="Path of Iron")
        walker = RosterEntryFactory()
        CharacterPathHistoryFactory(character=walker.character_sheet, path=path)
        CharacterPathHistoryFactory(character=walker.character_sheet, path=later)
        grant = PathCodexGrant.objects.create(path=path, entry=entry)

        self.assertEqual(grant_to_current_holders(grant), 1)
        self.assertTrue(_known(walker, entry))


class DistinctionHoldersTests(TestCase):
    def test_holder_learns(self):
        entry = CodexEntryFactory(name="Magical Scars")
        distinction = DistinctionFactory(name="Magical Scar")
        holder = RosterEntryFactory()
        CharacterDistinctionFactory(character=holder.character_sheet, distinction=distinction)
        grant = DistinctionCodexGrant.objects.create(distinction=distinction, entry=entry)

        self.assertEqual(grant_to_current_holders(grant), 1)
        self.assertTrue(_known(holder, entry))
