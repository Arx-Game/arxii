"""Tests for Wave 5 — GROUP/GLOBAL 'ANY member' auto-evaluation.

evaluate_auto_beats flips ACHIEVEMENT_HELD / CONDITION_HELD /
CODEX_ENTRY_UNLOCKED / CHARACTER_LEVEL_AT_LEAST beats in GROUP- and
GLOBAL-scope stories when any active member satisfies the predicate.
SUCCESS is sticky — removing a qualifying member doesn't un-flip a beat.
"""

from evennia.utils.test_resources import EvenniaTestCase

from world.achievements.factories import AchievementFactory, CharacterAchievementFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CharacterCodexKnowledgeFactory, CodexEntryFactory
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.gm.factories import GMTableFactory, GMTableMembershipFactory
from world.roster.factories import RosterEntryFactory, RosterFactory
from world.scenes.factories import PersonaFactory
from world.stories.constants import BeatOutcome, BeatPredicateType, StoryScope
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    GlobalStoryProgressFactory,
    GroupStoryProgressFactory,
    StoryFactory,
    StoryParticipationFactory,
)
from world.stories.services.beats import evaluate_auto_beats


def _make_group_story_with_member(gm_table, scope=StoryScope.GROUP):
    """Return (story, episode, progress) for a GROUP-scope story."""
    story = StoryFactory(scope=scope, character_sheet=None)
    episode = EpisodeFactory(chapter=ChapterFactory(story=story))
    progress = GroupStoryProgressFactory(
        story=story,
        gm_table=gm_table,
        current_episode=episode,
    )
    return story, episode, progress


class GroupScopeAchievementTests(EvenniaTestCase):
    def test_flips_when_any_member_has_achievement(self) -> None:
        member_sheet = CharacterSheetFactory()
        persona = PersonaFactory(character_sheet=member_sheet)
        table = GMTableFactory()
        GMTableMembershipFactory(table=table, persona=persona)
        _story, episode, progress = _make_group_story_with_member(table)

        achievement = AchievementFactory()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=achievement,
            outcome=BeatOutcome.UNSATISFIED,
        )
        CharacterAchievementFactory(character_sheet=member_sheet, achievement=achievement)

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_stays_unsatisfied_when_no_member_has_achievement(self) -> None:
        member_sheet = CharacterSheetFactory()
        persona = PersonaFactory(character_sheet=member_sheet)
        table = GMTableFactory()
        GMTableMembershipFactory(table=table, persona=persona)
        _story, episode, progress = _make_group_story_with_member(table)

        achievement = AchievementFactory()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=achievement,
            outcome=BeatOutcome.UNSATISFIED,
        )
        # Note: member does not have the achievement.
        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)


class GroupScopeConditionTests(EvenniaTestCase):
    def test_flips_when_any_member_has_condition(self) -> None:
        member_sheet = CharacterSheetFactory()
        persona = PersonaFactory(character_sheet=member_sheet)
        table = GMTableFactory()
        GMTableMembershipFactory(table=table, persona=persona)
        _story, episode, progress = _make_group_story_with_member(table)

        template = ConditionTemplateFactory()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=template,
            outcome=BeatOutcome.UNSATISFIED,
        )
        ConditionInstanceFactory(target=member_sheet.character, condition=template)

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)


class GroupScopeCodexTests(EvenniaTestCase):
    def test_flips_when_any_member_has_codex_entry(self) -> None:
        roster = RosterFactory()
        member_sheet = CharacterSheetFactory()
        roster_entry = RosterEntryFactory(character_sheet=member_sheet, roster=roster)
        persona = PersonaFactory(character_sheet=member_sheet)
        table = GMTableFactory()
        GMTableMembershipFactory(table=table, persona=persona)
        _story, episode, progress = _make_group_story_with_member(table)

        codex_entry = CodexEntryFactory()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CODEX_ENTRY_UNLOCKED,
            required_codex_entry=codex_entry,
            outcome=BeatOutcome.UNSATISFIED,
        )
        CharacterCodexKnowledgeFactory(
            roster_entry=roster_entry,
            entry=codex_entry,
            status=CodexKnowledgeStatus.KNOWN,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)


class GroupScopeLevelTests(EvenniaTestCase):
    def test_flips_when_any_member_at_level(self) -> None:
        member_sheet = CharacterSheetFactory()
        persona = PersonaFactory(character_sheet=member_sheet)
        table = GMTableFactory()
        GMTableMembershipFactory(table=table, persona=persona)
        _story, episode, progress = _make_group_story_with_member(table)

        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(
            character=member_sheet.character,
            character_class=char_class,
            level=5,
        )
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=5,
            outcome=BeatOutcome.UNSATISFIED,
        )

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)


class GlobalScopeTests(EvenniaTestCase):
    def test_flips_when_any_participant_has_condition(self) -> None:
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.GLOBAL, character_sheet=None)
        StoryParticipationFactory(story=story, character=sheet.character)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        progress = GlobalStoryProgressFactory(story=story, current_episode=episode)

        template = ConditionTemplateFactory()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=template,
            outcome=BeatOutcome.UNSATISFIED,
        )
        ConditionInstanceFactory(target=sheet.character, condition=template)

        evaluate_auto_beats(progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)


class StickySuccessTests(EvenniaTestCase):
    def test_member_leaving_does_not_unflip_success(self) -> None:
        """Once a beat is SUCCESS, removing the qualifying member does not un-flip."""
        member_sheet = CharacterSheetFactory()
        persona = PersonaFactory(character_sheet=member_sheet)
        table = GMTableFactory()
        membership = GMTableMembershipFactory(table=table, persona=persona)
        _story, episode, progress = _make_group_story_with_member(table)

        achievement = AchievementFactory()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=achievement,
            outcome=BeatOutcome.UNSATISFIED,
        )
        CharacterAchievementFactory(character_sheet=member_sheet, achievement=achievement)

        # First evaluation flips to SUCCESS.
        evaluate_auto_beats(progress)
        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

        # Member leaves; re-evaluation should not change outcome.
        from django.utils import timezone

        membership.left_at = timezone.now()
        membership.save()

        evaluate_auto_beats(progress)
        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)
