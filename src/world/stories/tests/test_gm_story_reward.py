"""Integration tests for the GM Story Reward convergence points (#2123).

Covers the three rev-1 award events (beat mark, episode resolve, story
completion) wired through record_gm_marked_outcome / resolve_episode /
complete_story, plus the shared players-served scaling + self-dealing guard
in world.stories.services.gm_rewards.
"""

from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory, GMTableMembershipFactory
from world.gm.models import GMRewardConfig
from world.progression.models import XPTransaction
from world.progression.types import ProgressionReason
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.stories.constants import BeatOutcome, BeatPredicateType, StoryMaturity, StoryScope
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    GroupStoryProgressFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
    seed_default_risk_calibrations,
)
from world.stories.services.beats import record_gm_marked_outcome, record_outcome_tier_completion
from world.stories.services.completion import complete_story
from world.stories.services.episodes import resolve_episode


def _character_gm_marked_setup():
    sheet = CharacterSheetFactory()
    episode = EpisodeFactory()
    story = episode.chapter.story
    story.scope = StoryScope.CHARACTER
    story.character_sheet = sheet
    story.save(update_fields=["scope", "character_sheet"])
    progress = StoryProgressFactory(story=story, character_sheet=sheet, current_episode=episode)
    beat = BeatFactory(
        episode=episode, predicate_type=BeatPredicateType.GM_MARKED, outcome=BeatOutcome.UNSATISFIED
    )
    return progress, beat, sheet


class BeatMarkRewardTests(EvenniaTestCase):
    """record_gm_marked_outcome credits GM Story Reward XP when resolved_by is set."""

    def test_character_scope_awards_beat_xp_per_player(self) -> None:
        progress, beat, _sheet = _character_gm_marked_setup()
        gm = GMProfileFactory()

        record_gm_marked_outcome(
            progress=progress, beat=beat, outcome=BeatOutcome.SUCCESS, resolved_by=gm
        )

        config = GMRewardConfig.load()
        txn = XPTransaction.objects.get(account=gm.account)
        self.assertEqual(txn.amount, config.beat_xp_per_player)
        self.assertEqual(txn.reason, ProgressionReason.GM_STORY_REWARD)
        self.assertNotIn(gm.account.username, txn.description)

    def test_no_resolved_by_awards_nothing(self) -> None:
        progress, beat, _sheet = _character_gm_marked_setup()
        record_gm_marked_outcome(progress=progress, beat=beat, outcome=BeatOutcome.SUCCESS)
        self.assertFalse(
            XPTransaction.objects.filter(reason=ProgressionReason.GM_STORY_REWARD).exists()
        )

    def test_self_dealing_gm_owns_the_character_awards_nothing(self) -> None:
        """A GM running their own solo CHARACTER-scope arc gets no reward."""
        progress, beat, sheet = _character_gm_marked_setup()
        gm = GMProfileFactory()
        sheet.character.db_account = gm.account
        sheet.character.save()

        record_gm_marked_outcome(
            progress=progress, beat=beat, outcome=BeatOutcome.SUCCESS, resolved_by=gm
        )

        self.assertFalse(
            XPTransaction.objects.filter(reason=ProgressionReason.GM_STORY_REWARD).exists()
        )

    def test_group_scope_scales_by_active_members_excluding_gms_own_persona(self) -> None:
        gm = GMProfileFactory()
        table = GMTableFactory(gm=gm)
        story = StoryFactory(scope=StoryScope.GROUP, primary_table=table)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        progress = GroupStoryProgressFactory(story=story, gm_table=table, current_episode=episode)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
        )

        # 3 real players.
        for _ in range(3):
            persona = PersonaFactory(persona_type=PersonaType.ESTABLISHED)
            GMTableMembershipFactory(table=table, persona=persona)
        # The GM's own persona is also seated — must not count as a player served.
        gm_persona = PersonaFactory(persona_type=PersonaType.ESTABLISHED)
        gm_persona.character_sheet.character.db_account = gm.account
        gm_persona.character_sheet.character.save()
        GMTableMembershipFactory(table=table, persona=gm_persona)

        record_gm_marked_outcome(
            progress=progress, beat=beat, outcome=BeatOutcome.SUCCESS, resolved_by=gm
        )

        config = GMRewardConfig.load()
        txn = XPTransaction.objects.get(account=gm.account)
        self.assertEqual(txn.amount, config.beat_xp_per_player * 3)

    def test_group_scope_caps_players_served_at_eight(self) -> None:
        """The players_served formula itself caps at 8, independent of the event cap."""
        from world.stories.services.gm_rewards import players_served_for_scope

        gm = GMProfileFactory()
        table = GMTableFactory(gm=gm)
        for _ in range(10):
            persona = PersonaFactory(persona_type=PersonaType.ESTABLISHED)
            GMTableMembershipFactory(table=table, persona=persona)

        players_served = players_served_for_scope(
            scope=StoryScope.GROUP, gm_profile=gm, gm_table=table
        )
        self.assertEqual(players_served, 8)

    def test_agm_marking_is_credited_not_the_lead_gm(self) -> None:
        """Whoever actually marks the beat is credited, per the spec's AGM story."""
        lead_gm = GMProfileFactory()
        agm = GMProfileFactory()
        progress, beat, _sheet = _character_gm_marked_setup()

        record_gm_marked_outcome(
            progress=progress, beat=beat, outcome=BeatOutcome.SUCCESS, resolved_by=agm
        )

        self.assertTrue(XPTransaction.objects.filter(account=agm.account).exists())
        self.assertFalse(XPTransaction.objects.filter(account=lead_gm.account).exists())

    def test_machine_graded_completion_never_awards(self) -> None:
        """record_outcome_tier_completion never passes resolved_by — no award, ever."""
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        progress = StoryProgressFactory(story=story, character_sheet=sheet, current_episode=episode)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        from world.traits.factories import CheckOutcomeFactory

        outcome_tier = CheckOutcomeFactory(success_level=6)

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=outcome_tier)

        self.assertFalse(
            XPTransaction.objects.filter(reason=ProgressionReason.GM_STORY_REWARD).exists()
        )


class EpisodeResolveRewardTests(EvenniaTestCase):
    """resolve_episode credits GM Story Reward XP alongside touch_gm_activity."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_risk_calibrations()

    def test_resolve_episode_awards_episode_xp(self) -> None:
        gm = GMProfileFactory()
        story = StoryFactory()
        chapter = ChapterFactory(story=story, is_active=True, maturity=StoryMaturity.PLOT)
        episode = EpisodeFactory(chapter=chapter)
        BeatFactory(episode=episode, predicate_type=BeatPredicateType.GM_MARKED)
        progress = StoryProgressFactory(story=story, current_episode=episode)
        transition = TransitionFactory(source_episode=episode)

        resolve_episode(progress=progress, chosen_transition=transition, resolved_by=gm)

        config = GMRewardConfig.load()
        txn = XPTransaction.objects.get(
            account=gm.account, reason=ProgressionReason.GM_STORY_REWARD
        )
        self.assertEqual(txn.amount, config.episode_xp_per_player)

    def test_resolve_episode_without_gm_profile_awards_nothing(self) -> None:
        story = StoryFactory()
        chapter = ChapterFactory(story=story, is_active=True, maturity=StoryMaturity.PLOT)
        episode = EpisodeFactory(chapter=chapter)
        BeatFactory(episode=episode, predicate_type=BeatPredicateType.GM_MARKED)
        progress = StoryProgressFactory(story=story, current_episode=episode)
        transition = TransitionFactory(source_episode=episode)

        resolve_episode(progress=progress, chosen_transition=transition, resolved_by=None)

        self.assertFalse(
            XPTransaction.objects.filter(reason=ProgressionReason.GM_STORY_REWARD).exists()
        )


class StoryCompletionRewardTests(EvenniaTestCase):
    """complete_story credits the story's primary_table.gm."""

    def test_complete_story_awards_story_completion_xp(self) -> None:
        gm = GMProfileFactory()
        table = GMTableFactory(gm=gm)
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet, primary_table=table)

        complete_story(story=story)

        config = GMRewardConfig.load()
        txn = XPTransaction.objects.get(
            account=gm.account, reason=ProgressionReason.GM_STORY_REWARD
        )
        self.assertEqual(txn.amount, config.story_completion_xp_per_player)

    def test_complete_story_orphaned_story_awards_nothing(self) -> None:
        story = StoryFactory(primary_table=None)
        complete_story(story=story)
        self.assertFalse(
            XPTransaction.objects.filter(reason=ProgressionReason.GM_STORY_REWARD).exists()
        )

    def test_complete_story_idempotent_only_awards_once(self) -> None:
        gm = GMProfileFactory()
        table = GMTableFactory(gm=gm)
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet, primary_table=table)

        complete_story(story=story)
        complete_story(story=story)

        self.assertEqual(
            XPTransaction.objects.filter(
                account=gm.account, reason=ProgressionReason.GM_STORY_REWARD
            ).count(),
            1,
        )
