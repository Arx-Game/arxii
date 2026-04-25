"""Tests for conditions → stories reactivity wiring.

apply_condition and remove_condition notify the stories reactivity
service so active stories with CONDITION_HELD beats re-evaluate when
conditions are applied or removed.
"""

from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.services import apply_condition, remove_condition
from world.stories.constants import BeatOutcome, BeatPredicateType, StoryScope
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
)


class ApplyConditionReactivityTests(EvenniaTestCase):
    def test_apply_condition_flips_condition_held_beat(self) -> None:
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        StoryProgressFactory(
            story=story,
            character_sheet=sheet,
            current_episode=episode,
        )
        template = ConditionTemplateFactory()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=template,
            outcome=BeatOutcome.UNSATISFIED,
        )

        apply_condition(sheet.character, template)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_apply_condition_on_non_sheet_target_is_noop(self) -> None:
        """Conditions on an NPC ObjectDB without a sheet shouldn't crash."""
        from evennia_extensions.factories import CharacterFactory

        # A plain Character (no sheet_data) should quietly skip the hook.
        npc = CharacterFactory()
        template = ConditionTemplateFactory()
        # Should not raise.
        apply_condition(npc, template)


class RemoveConditionReactivityTests(EvenniaTestCase):
    def test_remove_condition_runs_without_error(self) -> None:
        """Remove doesn't un-flip SUCCESS (sticky) but the hook fires cleanly."""
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        StoryProgressFactory(
            story=story,
            character_sheet=sheet,
            current_episode=episode,
        )
        template = ConditionTemplateFactory()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=template,
            outcome=BeatOutcome.SUCCESS,
        )
        apply_condition(sheet.character, template)
        remove_condition(sheet.character, template)

        beat.refresh_from_db()
        # SUCCESS is sticky — no current predicate un-flips a satisfied beat.
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)
