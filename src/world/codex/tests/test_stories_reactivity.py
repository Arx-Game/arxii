"""Tests for codex → stories reactivity wiring.

``world.codex.services.add_codex_progress`` notifies the stories reactivity
service when status transitions to KNOWN, so active stories with
CODEX_ENTRY_UNLOCKED beats auto-flip.
"""

from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.codex.factories import CharacterCodexKnowledgeFactory, CodexEntryFactory
from world.codex.services import add_codex_progress
from world.roster.factories import RosterEntryFactory, RosterFactory
from world.stories.constants import BeatOutcome, BeatPredicateType, StoryScope
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
)


class CodexAddProgressReactivityTests(EvenniaTestCase):
    def test_known_transition_flips_codex_beat(self) -> None:
        roster = RosterFactory()
        sheet = CharacterSheetFactory()
        roster_entry = RosterEntryFactory(character_sheet=sheet, roster=roster)
        codex_entry = CodexEntryFactory(learn_threshold=10)

        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        StoryProgressFactory(
            story=story,
            character_sheet=sheet,
            current_episode=episode,
        )
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CODEX_ENTRY_UNLOCKED,
            required_codex_entry=codex_entry,
            outcome=BeatOutcome.UNSATISFIED,
        )

        knowledge = CharacterCodexKnowledgeFactory(
            roster_entry=roster_entry,
            entry=codex_entry,
            learning_progress=5,
        )
        # Flip to KNOWN via the service — the hook fires here.
        add_codex_progress(knowledge=knowledge, amount=5)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_partial_progress_does_not_fire_hook(self) -> None:
        roster = RosterFactory()
        sheet = CharacterSheetFactory()
        roster_entry = RosterEntryFactory(character_sheet=sheet, roster=roster)
        codex_entry = CodexEntryFactory(learn_threshold=10)

        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        StoryProgressFactory(
            story=story,
            character_sheet=sheet,
            current_episode=episode,
        )
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CODEX_ENTRY_UNLOCKED,
            required_codex_entry=codex_entry,
            outcome=BeatOutcome.UNSATISFIED,
        )
        knowledge = CharacterCodexKnowledgeFactory(
            roster_entry=roster_entry,
            entry=codex_entry,
            learning_progress=0,
        )
        add_codex_progress(knowledge=knowledge, amount=3)  # still UNCOVERED

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)
