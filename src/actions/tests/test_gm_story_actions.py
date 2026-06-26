"""Tests for GM story lifecycle actions (#1495)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.roster.factories import RosterTenureFactory
from world.stories.constants import (
    AssistantClaimStatus,
    BeatOutcome,
    BeatPredicateType,
    StoryMaturity,
    StoryScope,
    TransitionMode,
)
from world.stories.factories import (
    AssistantGMClaimFactory,
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    GroupStoryProgressFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
)
from world.stories.models import BeatCompletion, EpisodeResolution
from world.stories.types import StoryStatus


def _make_room(label: str = "Room") -> object:
    return ObjectDBFactory(
        db_key=label,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _make_actor_with_account(
    db_key: str,
    room: object,
    account: object,
) -> tuple[object, object]:
    """Create a PC in *room* whose ``active_account`` is *account*."""
    char = CharacterFactory(db_key=db_key, location=room)
    sheet = CharacterSheetFactory(character=char)
    entry = RosterTenureFactory(
        roster_entry__character_sheet=sheet,
        player_data__account=account,
        end_date=None,
    ).roster_entry
    return char, entry.character_sheet


class GMStoryActionTestBase(TestCase):
    """Shared fixture for story GM lifecycle action tests."""

    def setUp(self) -> None:
        self.room = _make_room("GMStoryRoom")

        # Lead GM account / actor
        self.lead_gm_account = AccountFactory(username="storylead")
        self.lead_gm_profile = GMProfileFactory(account=self.lead_gm_account)
        self.gm_table = GMTableFactory(gm=self.lead_gm_profile)
        self.lead_gm_actor, self.lead_gm_sheet = _make_actor_with_account(
            "story_lead_actor",
            self.room,
            self.lead_gm_account,
        )

        # Staff account / actor
        self.staff_account = AccountFactory(username="storystaff", is_staff=True)
        self.staff_actor, _ = _make_actor_with_account(
            "story_staff_actor",
            self.room,
            self.staff_account,
        )

        # Non-GM player account / actor
        self.player_account = AccountFactory(username="storyplayer")
        self.player_actor, _ = _make_actor_with_account(
            "story_player_actor",
            self.room,
            self.player_account,
        )

        # Story with Lead GM on primary table
        self.story = StoryFactory(
            owners=[self.lead_gm_account],
            scope=StoryScope.CHARACTER,
            primary_table=self.gm_table,
            status=StoryStatus.ACTIVE,
        )
        self.chapter = ChapterFactory(story=self.story)
        self.ep1 = EpisodeFactory(chapter=self.chapter, order=1)
        self.ep2 = EpisodeFactory(chapter=self.chapter, order=2)

        # Active progress on the story
        self.progress = StoryProgressFactory(
            story=self.story,
            character_sheet=self.lead_gm_sheet,
            current_episode=self.ep1,
            is_active=True,
        )


class CompleteStoryActionTests(GMStoryActionTestBase):
    """CompleteStoryAction concludes a story."""

    def test_lead_gm_can_complete_story(self) -> None:
        from actions.definitions.gm_stories import CompleteStoryAction

        result = CompleteStoryAction().run(self.lead_gm_actor, story_id=self.story.pk)
        self.assertTrue(result.success, result.message)
        self.story.refresh_from_db()
        self.assertEqual(self.story.status, StoryStatus.COMPLETED)
        self.assertIsNotNone(self.story.completed_at)

    def test_staff_can_complete_story(self) -> None:
        from actions.definitions.gm_stories import CompleteStoryAction

        result = CompleteStoryAction().run(self.staff_actor, story_id=self.story.pk)
        self.assertTrue(result.success, result.message)
        self.story.refresh_from_db()
        self.assertEqual(self.story.status, StoryStatus.COMPLETED)

    def test_non_gm_denied(self) -> None:
        from actions.definitions.gm_stories import CompleteStoryAction

        result = CompleteStoryAction().run(self.player_actor, story_id=self.story.pk)
        self.assertFalse(result.success)
        self.story.refresh_from_db()
        self.assertEqual(self.story.status, StoryStatus.ACTIVE)


class ResolveEpisodeActionTests(GMStoryActionTestBase):
    """ResolveEpisodeAction advances progress through a transition."""

    def setUp(self) -> None:
        super().setUp()
        self.transition = TransitionFactory(
            source_episode=self.ep1,
            target_episode=self.ep2,
            mode=TransitionMode.AUTO,
        )

    def test_lead_gm_can_resolve_auto_transition(self) -> None:
        from actions.definitions.gm_stories import ResolveEpisodeAction

        result = ResolveEpisodeAction().run(self.lead_gm_actor, episode_id=self.ep1.pk)
        self.assertTrue(result.success, result.message)
        self.assertTrue(EpisodeResolution.objects.filter(episode=self.ep1).exists())
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.current_episode_id, self.ep2.pk)

    def test_staff_can_resolve_episode(self) -> None:
        from actions.definitions.gm_stories import ResolveEpisodeAction

        result = ResolveEpisodeAction().run(self.staff_actor, episode_id=self.ep1.pk)
        self.assertTrue(result.success, result.message)

    def test_non_gm_denied(self) -> None:
        from actions.definitions.gm_stories import ResolveEpisodeAction

        result = ResolveEpisodeAction().run(self.player_actor, episode_id=self.ep1.pk)
        self.assertFalse(result.success)
        self.assertFalse(EpisodeResolution.objects.filter(episode=self.ep1).exists())

    def test_gm_choice_requires_transition_id(self) -> None:
        from actions.definitions.gm_stories import ResolveEpisodeAction

        gm_choice_transition = TransitionFactory(
            source_episode=self.ep1,
            target_episode=self.ep2,
            mode=TransitionMode.GM_CHOICE,
        )
        # Reset progress to the source episode for this scenario.
        self.progress.current_episode = self.ep1
        self.progress.save(update_fields=["current_episode", "last_advanced_at"])

        result = ResolveEpisodeAction().run(self.lead_gm_actor, episode_id=self.ep1.pk)
        self.assertFalse(result.success)

        result = ResolveEpisodeAction().run(
            self.lead_gm_actor,
            episode_id=self.ep1.pk,
            chosen_transition_id=gm_choice_transition.pk,
        )
        self.assertTrue(result.success, result.message)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.current_episode_id, self.ep2.pk)

    def test_missing_progress_returns_failure(self) -> None:
        from actions.definitions.gm_stories import ResolveEpisodeAction

        self.progress.delete()
        result = ResolveEpisodeAction().run(self.lead_gm_actor, episode_id=self.ep1.pk)
        self.assertFalse(result.success)

    def test_group_scope_multiple_active_records_uses_first(self) -> None:
        """GROUP stories with multiple active tables are handled by the service."""
        from actions.definitions.gm_stories import ResolveEpisodeAction

        group_story = StoryFactory(
            owners=[self.lead_gm_account],
            scope=StoryScope.GROUP,
            primary_table=self.gm_table,
            status=StoryStatus.ACTIVE,
        )
        chapter = ChapterFactory(story=group_story)
        ep1 = EpisodeFactory(chapter=chapter, order=1)
        ep2 = EpisodeFactory(chapter=chapter, order=2)
        TransitionFactory(source_episode=ep1, target_episode=ep2, mode=TransitionMode.AUTO)
        other_table = GMTableFactory(gm=GMProfileFactory())
        progress1 = GroupStoryProgressFactory(
            story=group_story,
            gm_table=self.gm_table,
            current_episode=ep1,
            is_active=True,
        )
        progress2 = GroupStoryProgressFactory(
            story=group_story,
            gm_table=other_table,
            current_episode=ep1,
            is_active=True,
        )

        result = ResolveEpisodeAction().run(self.lead_gm_actor, episode_id=ep1.pk)

        self.assertTrue(result.success, result.message)
        progress1.refresh_from_db()
        progress2.refresh_from_db()
        advanced = [p for p in (progress1, progress2) if p.current_episode_id == ep2.pk]
        self.assertEqual(len(advanced), 1)


class PromoteEpisodeActionTests(GMStoryActionTestBase):
    """PromoteEpisodeAction changes episode maturity."""

    def test_lead_gm_can_promote_to_plot(self) -> None:
        from actions.definitions.gm_stories import PromoteEpisodeAction

        episode = EpisodeFactory(
            chapter=self.chapter,
            order=10,
            maturity=StoryMaturity.OUTLINE,
            resting_conclusion="The path forks ahead.",
        )
        TransitionFactory(source_episode=episode, target_episode=self.ep2)

        result = PromoteEpisodeAction().run(
            self.lead_gm_actor,
            episode_id=episode.pk,
            target=StoryMaturity.PLOT,
        )
        self.assertTrue(result.success, result.message)
        episode.refresh_from_db()
        self.assertEqual(episode.maturity, StoryMaturity.PLOT)

    def test_staff_can_promote_episode(self) -> None:
        from actions.definitions.gm_stories import PromoteEpisodeAction

        episode = EpisodeFactory(
            chapter=self.chapter,
            order=11,
            maturity=StoryMaturity.OUTLINE,
            resting_conclusion="A quiet moment.",
        )
        TransitionFactory(source_episode=episode, target_episode=self.ep2)

        result = PromoteEpisodeAction().run(
            self.staff_actor,
            episode_id=episode.pk,
            target=StoryMaturity.PLOT,
        )
        self.assertTrue(result.success, result.message)

    def test_non_gm_denied(self) -> None:
        from actions.definitions.gm_stories import PromoteEpisodeAction

        episode = EpisodeFactory(
            chapter=self.chapter,
            order=12,
            maturity=StoryMaturity.OUTLINE,
            resting_conclusion="A quiet moment.",
        )
        TransitionFactory(source_episode=episode, target_episode=self.ep2)

        result = PromoteEpisodeAction().run(
            self.player_actor,
            episode_id=episode.pk,
            target=StoryMaturity.PLOT,
        )
        self.assertFalse(result.success)
        episode.refresh_from_db()
        self.assertEqual(episode.maturity, StoryMaturity.OUTLINE)

    def test_plot_gate_blocks_promotion(self) -> None:
        from actions.definitions.gm_stories import PromoteEpisodeAction

        episode = EpisodeFactory(
            chapter=self.chapter,
            order=13,
            maturity=StoryMaturity.PITCH,
            resting_conclusion="",
        )

        result = PromoteEpisodeAction().run(
            self.lead_gm_actor,
            episode_id=episode.pk,
            target=StoryMaturity.PLOT,
        )
        self.assertFalse(result.success)
        episode.refresh_from_db()
        self.assertEqual(episode.maturity, StoryMaturity.PITCH)


class MarkBeatActionTests(GMStoryActionTestBase):
    """MarkBeatAction resolves a GM_MARKED beat."""

    def setUp(self) -> None:
        super().setUp()
        self.beat = BeatFactory(
            episode=self.ep1,
            predicate_type=BeatPredicateType.GM_MARKED,
            agm_eligible=True,
        )

    def test_lead_gm_can_mark_beat(self) -> None:
        from actions.definitions.gm_stories import MarkBeatAction

        result = MarkBeatAction().run(
            self.lead_gm_actor,
            beat_id=self.beat.pk,
            outcome=BeatOutcome.SUCCESS,
        )
        self.assertTrue(result.success, result.message)
        self.beat.refresh_from_db()
        self.assertEqual(self.beat.outcome, BeatOutcome.SUCCESS)
        self.assertTrue(BeatCompletion.objects.filter(beat=self.beat).exists())

    def test_staff_can_mark_beat(self) -> None:
        from actions.definitions.gm_stories import MarkBeatAction

        result = MarkBeatAction().run(
            self.staff_actor,
            beat_id=self.beat.pk,
            outcome=BeatOutcome.SUCCESS,
        )
        self.assertTrue(result.success, result.message)

    def test_approved_agm_can_mark_beat(self) -> None:
        from actions.definitions.gm_stories import MarkBeatAction

        agm_account = AccountFactory(username="agm")
        agm_profile = GMProfileFactory(account=agm_account)
        agm_actor, _ = _make_actor_with_account(
            "agm_actor",
            self.room,
            agm_account,
        )
        AssistantGMClaimFactory(
            beat=self.beat,
            assistant_gm=agm_profile,
            status=AssistantClaimStatus.APPROVED,
            approved_by=self.lead_gm_profile,
        )

        result = MarkBeatAction().run(
            agm_actor,
            beat_id=self.beat.pk,
            outcome=BeatOutcome.SUCCESS,
        )
        self.assertTrue(result.success, result.message)

    def test_unapproved_agm_denied(self) -> None:
        from actions.definitions.gm_stories import MarkBeatAction

        agm_account = AccountFactory(username="agm_requested")
        agm_profile = GMProfileFactory(account=agm_account)
        agm_actor, _ = _make_actor_with_account(
            "agm_requested_actor",
            self.room,
            agm_account,
        )
        AssistantGMClaimFactory(
            beat=self.beat,
            assistant_gm=agm_profile,
            status=AssistantClaimStatus.REQUESTED,
        )

        result = MarkBeatAction().run(
            agm_actor,
            beat_id=self.beat.pk,
            outcome=BeatOutcome.SUCCESS,
        )
        self.assertFalse(result.success)

    def test_non_gm_denied(self) -> None:
        from actions.definitions.gm_stories import MarkBeatAction

        result = MarkBeatAction().run(
            self.player_actor,
            beat_id=self.beat.pk,
            outcome=BeatOutcome.SUCCESS,
        )
        self.assertFalse(result.success)
