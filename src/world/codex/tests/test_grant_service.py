"""Tests for grant_codex_entry, the single sanctioned path to KNOWN (#2880).

Seven callers used to create ``CharacterCodexKnowledge`` rows with
``status=KNOWN`` directly. ``add_progress`` returns early unless the row is
UNCOVERED, and it is where #939 deliberately put the KNOWN-transition hook, so
every one of those callers skipped both the stories reactivity hook and the
``learned_at`` stamp.
"""

from unittest.mock import patch

from django.test import TestCase

from world.achievements.factories import AchievementFactory
from world.achievements.models import CharacterAchievement
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CodexEntryFactory
from world.codex.models import CharacterCodexKnowledge
from world.codex.services import grant_codex_entry
from world.narrative.models import NarrativeMessage
from world.roster.factories import RosterEntryFactory, RosterTenureFactory

HOOK = "world.stories.services.reactivity.on_codex_entry_unlocked"


class GrantCodexEntryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.entry = CodexEntryFactory(name="Granted Entry")

    def test_lands_known(self):
        roster_entry = RosterEntryFactory()

        knowledge, newly_known = grant_codex_entry(roster_entry, self.entry)

        self.assertTrue(newly_known)
        self.assertEqual(knowledge.status, CodexKnowledgeStatus.KNOWN)

    def test_stamps_learned_at(self):
        """The column a direct ``status=KNOWN`` create left null."""
        roster_entry = RosterEntryFactory()

        knowledge, _ = grant_codex_entry(roster_entry, self.entry)

        self.assertIsNotNone(knowledge.learned_at)

    def test_fires_the_stories_unlock_hook(self):
        """The whole reason this wrapper exists rather than a KNOWN create."""
        roster_entry = RosterEntryFactory()

        with patch(HOOK) as hook:
            grant_codex_entry(roster_entry, self.entry)

        hook.assert_called_once()
        self.assertEqual(hook.call_args.args[1], self.entry)

    def test_repeat_grant_is_a_noop_and_does_not_refire_the_hook(self):
        roster_entry = RosterEntryFactory()
        grant_codex_entry(roster_entry, self.entry)

        with patch(HOOK) as hook:
            _, newly_known = grant_codex_entry(roster_entry, self.entry)

        self.assertFalse(newly_known)
        hook.assert_not_called()
        self.assertEqual(
            CharacterCodexKnowledge.objects.filter(
                roster_entry=roster_entry, entry=self.entry
            ).count(),
            1,
        )

    def test_completes_an_entry_the_character_was_part_way_through(self):
        """A researcher who then gets the entry granted lands KNOWN, once."""
        roster_entry = RosterEntryFactory()
        partial = CharacterCodexKnowledge.objects.create(
            roster_entry=roster_entry,
            entry=self.entry,
            status=CodexKnowledgeStatus.UNCOVERED,
        )
        partial.add_progress(1)

        knowledge, newly_known = grant_codex_entry(roster_entry, self.entry)

        self.assertTrue(newly_known)
        self.assertEqual(knowledge.pk, partial.pk)
        self.assertEqual(knowledge.status, CodexKnowledgeStatus.KNOWN)

    def test_records_the_teacher_when_given_one(self):
        roster_entry = RosterEntryFactory()
        tenure = RosterTenureFactory()

        knowledge, _ = grant_codex_entry(roster_entry, self.entry, learned_from=tenure)

        self.assertEqual(knowledge.learned_from, tenure)


class GrantCodexEntryAnnouncesAccessChangeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.entry = CodexEntryFactory(name="Announced Entry")

    def test_newly_known_sends_the_gained_narrative_message(self):
        roster_entry = RosterEntryFactory()

        grant_codex_entry(roster_entry, self.entry)

        msg = NarrativeMessage.objects.latest("id")
        self.assertIn("Announced Entry", msg.body)

    def test_newly_known_with_achievement_and_live_tenure_fires_discovery(self):
        ach = AchievementFactory(hidden=True)
        entry = CodexEntryFactory(name="Ceremony Entry", discovery_achievement=ach)
        roster_entry = RosterEntryFactory()
        RosterTenureFactory(roster_entry=roster_entry, end_date=None)

        grant_codex_entry(roster_entry, entry)

        self.assertTrue(
            CharacterAchievement.objects.filter(
                character_sheet=roster_entry.character_sheet, achievement=ach
            ).exists()
        )

    def test_repeat_grant_does_not_resend_the_message(self):
        roster_entry = RosterEntryFactory()
        grant_codex_entry(roster_entry, self.entry)
        count_after_first = NarrativeMessage.objects.count()

        grant_codex_entry(roster_entry, self.entry)

        self.assertEqual(NarrativeMessage.objects.count(), count_after_first)

    def test_beginnings_catalog_entry_does_not_fire_discovery_through_grant_codex_entry(self):
        from world.achievements.factories import AchievementFactory
        from world.codex.factories import BeginningsCodexGrantFactory

        ach = AchievementFactory(hidden=True)
        entry = CodexEntryFactory(discovery_achievement=ach)
        BeginningsCodexGrantFactory(entry=entry)
        roster_entry = RosterEntryFactory()
        RosterTenureFactory(roster_entry=roster_entry, end_date=None)

        grant_codex_entry(roster_entry, entry)

        self.assertFalse(CharacterAchievement.objects.filter(achievement=ach).exists())
