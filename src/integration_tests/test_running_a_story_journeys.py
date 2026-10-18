"""Journeys for the stories tranche (#3657, tranche 4, step 1): a player reading her
own story while her Lead GM runs it beat by beat, the GM calling the canon on a
story's impact, and a GM opening a scene room for her players. Each types what a
player types or sends what the web client sends, and asserts what the player and
the GM were told."""

from __future__ import annotations

from integration_tests.harness import JourneyCase
from world.gm.constants import GMLevel
from world.gm.factories import (
    GMLevelCapFactory,
    GMProfileFactory,
    GMTableFactory,
    seed_default_gm_level_caps,
)
from world.instances.models import InstancedRoom
from world.narrative.models import NarrativeMessageDelivery
from world.progression.models import XPTransaction
from world.progression.types import ProgressionReason
from world.stories.constants import (
    AssistantClaimStatus,
    BeatOutcome,
    BeatPredicateType,
    BeatVisibility,
    CanonReviewStatus,
    StoryMaturity,
    StoryScope,
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
from world.stories.models import CanonReview, EpisodeResolution
from world.stories.types import StoryStatus


class _StoryTable(JourneyCase):
    """Ysmay has a personal story; Ravenna, an approved GM, runs it from her table."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.ravenna = self.make_player("Ravenna", room=self.lantern)
        self.watch(self.ysmay, self.hobb)
        self.gm_profile = GMProfileFactory(account=self.ravenna.db_account)
        self.table = GMTableFactory(gm=self.gm_profile, name="Ravenna's Table")
        self.story = StoryFactory(
            title="The Lantern Debt",
            scope=StoryScope.CHARACTER,
            character_sheet=self.ysmay.sheet_data,
            primary_table=self.table,
        )
        self.chapter = ChapterFactory(story=self.story, title="Debts", order=1, is_active=True)
        self.first = EpisodeFactory(
            chapter=self.chapter, title="The First Knock", order=1, is_active=True
        )
        self.second = EpisodeFactory(chapter=self.chapter, title="The Second Knock", order=2)
        TransitionFactory(source_episode=self.first, target_episode=self.second)
        self.beat = BeatFactory(
            episode=self.first,
            player_hint="Find out who knocked",
            player_resolution_text="The knocker is found: a debt collector from the docks.",
        )
        self.progress = StoryProgressFactory(
            story=self.story, character_sheet=self.ysmay.sheet_data, current_episode=self.first
        )


class RunningAStory(_StoryTable):
    def test_she_reads_her_story_while_the_gm_runs_it(self) -> None:
        told = self.telnet(self.ysmay, "story")
        self.assertIn("Your active stories:", told)
        self.assertIn(f'[{self.story.pk}] The Lantern Debt — currently in "The First Knock"', told)
        self.assertIn("You have no active stories.", self.telnet(self.hobb, "story"))

        self.assertIn(f"[{self.story.pk}] The Lantern Debt", self.telnet(self.ysmay, "story list"))
        self.assertIn("Usage: story <subcommand>", self.telnet(self.ysmay, "story frobnicate"))

        hidden = BeatFactory(
            episode=self.first, order=9, player_hint="", visibility=BeatVisibility.SECRET
        )
        told = self.telnet(self.ysmay, f"story beats {self.first.pk}")
        self.assertIn(f"Beats:\n  [{self.beat.pk}] Find out who knocked (unsatisfied)", told)
        # A secret beat with no hint is listed, but not by name.
        self.assertIn(f"  [{hidden.pk}] (Hidden Beat) (unsatisfied)", told)
        self.assertIn(
            "That's not one of your active stories.",
            self.telnet(self.ysmay, f"story beats {self.second.pk}"),
        )
        self.assertIn(
            "An episode must be specified by its numeric ID.",
            self.telnet(self.ysmay, "story beats first"),
        )
        self.assertIn("Usage: story beats <episode-id>.", self.telnet(self.ysmay, "story beats"))

        self.assertIn(
            "A beat must be specified by its numeric ID.",
            self.telnet(self.ravenna, "story mark abc success"),
        )
        told = self.telnet(self.hobb, f"story mark {self.beat.pk} success")
        self.assertIn(
            "Only the story's Lead GM, staff, or an approved Assistant GM may mark a beat.", told
        )
        told = self.telnet(self.ravenna, f"story mark {self.beat.pk} success The collector.")
        self.assertIn("Beat marked Success.", told)
        self.beat.refresh_from_db()
        self.assertEqual(self.beat.outcome, BeatOutcome.SUCCESS)
        # The narration is pushed to a connected session; a harness character has
        # none, so the queued copy her next login delivers is the record to read.
        queued = NarrativeMessageDelivery.objects.filter(
            recipient_character_sheet=self.ysmay.sheet_data,
            message__body="The knocker is found: a debt collector from the docks.",
        )
        self.assertTrue(queued.exists())
        self.assertFalse(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=self.hobb.sheet_data
            ).exists()
        )
        self.assertIn(
            f"[{self.beat.pk}] Find out who knocked (success)",
            self.telnet(self.ysmay, f"story beats {self.first.pk}"),
        )
        self.assertIn(
            "Invalid beat outcome.", self.telnet(self.ravenna, f"story mark {self.beat.pk} maybe")
        )
        self.assertIn("Usage: story mark", self.telnet(self.ravenna, "story mark"))

        self.assertIn(
            "Usage: story resolve <episode-id> [notes]", self.telnet(self.ravenna, "story resolve")
        )
        told = self.telnet(self.ravenna, f"story resolve {self.first.pk} The door swings open.")
        self.assertIn("Episode 'The First Knock' resolved.", told)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.current_episode_id, self.second.pk)
        self.assertIn('currently in "The Second Knock"', self.telnet(self.ysmay, "story"))
        self.assertIn(
            "Only the story's Lead GM or staff may do that.",
            self.telnet(self.hobb, f"story resolve {self.second.pk}"),
        )

        self.assertIn(
            "Usage: story complete <story-id>", self.telnet(self.ravenna, "story complete")
        )
        # A story may be named by its title, any case, in place of its id.
        told = self.telnet(self.ravenna, "story complete the lantern debt")
        self.assertIn("Story 'The Lantern Debt' completed.", told)
        self.story.refresh_from_db()
        self.assertEqual(self.story.status, StoryStatus.COMPLETED)
        self.assertIn(
            "Only the story's Lead GM or staff may do that.",
            self.telnet(self.hobb, f"story complete {self.story.pk}"),
        )

    def test_an_episode_is_promoted_through_its_maturities(self) -> None:
        draft = EpisodeFactory(
            chapter=self.chapter,
            title="The Reckoning",
            order=3,
            maturity=StoryMaturity.OUTLINE,
            resting_conclusion="The debt is paid in full, one way or another.",
            is_ending=True,
        )
        told = self.telnet(self.ravenna, f"story promote {draft.pk} plot")
        self.assertIn("Episode 'The Reckoning' promoted to Plot.", told)
        draft.refresh_from_db()
        self.assertEqual(draft.maturity, StoryMaturity.PLOT)
        self.assertIn(
            "Invalid target maturity.",
            self.telnet(self.ravenna, f"story promote {draft.pk} sideways"),
        )
        self.assertIn(
            "Usage: story promote", self.telnet(self.ravenna, f"story promote {draft.pk}")
        )
        self.assertIn(
            "Only the story's Lead GM or staff may do that.",
            self.telnet(self.hobb, f"story promote {draft.pk} plot"),
        )

    def test_the_web_marks_the_same_beat(self) -> None:
        result = self.web(self.ravenna, "mark_beat", beat_id=self.beat.pk, outcome="success")
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, "Beat marked Success.")
        result = self.web(self.hobb, "mark_beat", beat_id=self.beat.pk, outcome="failure")
        self.assertFalse(result.detail.success)

    def staff(self):
        marrow = self.make_player("Marrow", room=self.lantern)
        account = marrow.db_account
        account.is_staff = True
        account.save(update_fields=["is_staff"])
        return marrow

    def rewarded(self, character) -> bool:
        return XPTransaction.objects.filter(
            account=character.db_account, reason=ProgressionReason.GM_STORY_REWARD
        ).exists()

    def test_an_assistant_marks_only_what_she_is_cleared_for_and_is_the_one_credited(
        self,
    ) -> None:
        second_beat = BeatFactory(
            episode=self.first,
            order=2,
            player_hint="Ask the collector's name",
            predicate_type=BeatPredicateType.GM_MARKED,
            agm_eligible=True,
        )
        hobb_gm = GMProfileFactory(account=self.hobb.db_account)
        claim = AssistantGMClaimFactory(
            beat=second_beat, assistant_gm=hobb_gm, status=AssistantClaimStatus.REQUESTED
        )
        self.assertIn(
            "Only the story's Lead GM, staff, or an approved Assistant GM may mark a beat.",
            self.telnet(self.hobb, f"story mark {second_beat.pk} success"),
        )
        claim.status = AssistantClaimStatus.APPROVED
        claim.approved_by = self.gm_profile
        claim.save(update_fields=["status", "approved_by"])
        self.assertIn(
            "Beat marked Success.", self.telnet(self.hobb, f"story mark {second_beat.pk} success")
        )
        second_beat.refresh_from_db()
        self.assertEqual(second_beat.outcome, BeatOutcome.SUCCESS)
        self.assertTrue(self.rewarded(self.hobb))
        self.assertFalse(self.rewarded(self.ravenna))

    def test_staff_run_any_story(self) -> None:
        marrow = self.staff()
        draft = EpisodeFactory(
            chapter=self.chapter,
            title="The Reckoning",
            order=3,
            maturity=StoryMaturity.OUTLINE,
            resting_conclusion="The debt is paid.",
            is_ending=True,
        )
        self.assertIn(
            "Episode 'The Reckoning' promoted to Plot.",
            self.telnet(marrow, f"story promote {draft.pk} plot"),
        )
        self.assertIn(
            "Beat marked Failure.", self.telnet(marrow, f"story mark {self.beat.pk} failure")
        )
        self.assertIn(
            "Episode 'The First Knock' resolved.",
            self.telnet(marrow, f"story resolve {self.first.pk}"),
        )
        self.assertIn(
            "Story 'The Lantern Debt' completed.",
            self.telnet(marrow, f"story complete {self.story.pk}"),
        )
        self.story.refresh_from_db()
        self.assertEqual(self.story.status, StoryStatus.COMPLETED)

    def test_the_plot_gate_the_routing_and_a_story_nobody_is_in(self) -> None:
        pitch = EpisodeFactory(
            chapter=self.chapter, title="A Loose Thread", order=4, maturity=StoryMaturity.PITCH
        )
        self.assertIn(
            "This episode is not ready to be promoted to Plot. It needs a resting conclusion "
            "and either an outbound transition or an explicit ending.",
            self.telnet(self.ravenna, f"story promote {pitch.pk} plot"),
        )
        pitch.refresh_from_db()
        self.assertEqual(pitch.maturity, StoryMaturity.PITCH)

        # The author routes the story, never the GM after the fact: with two ways out of
        # an episode, the lowest-ordered transition is the one taken.
        third = EpisodeFactory(chapter=self.chapter, title="The Third Knock", order=3)
        TransitionFactory(source_episode=self.first, target_episode=third, order=1)
        self.assertIn(
            "Episode 'The First Knock' resolved.",
            self.telnet(self.ravenna, f"story resolve {self.first.pk}"),
        )
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.current_episode_id, self.second.pk)
        self.assertTrue(EpisodeResolution.objects.filter(episode=self.first).exists())

        self.progress.delete()
        self.assertIn(
            "No active progress record found for this story.",
            self.telnet(self.ravenna, f"story resolve {self.second.pk}"),
        )

    def test_a_gm_running_her_own_arc_earns_nothing_for_it(self) -> None:
        own = StoryFactory(
            title="Ravenna's Reckoning",
            scope=StoryScope.CHARACTER,
            character_sheet=self.ravenna.sheet_data,
            primary_table=self.table,
        )
        episode = EpisodeFactory(chapter__story=own, title="Alone", order=1, is_active=True)
        beat = BeatFactory(
            episode=episode, player_hint="Face it", predicate_type=BeatPredicateType.GM_MARKED
        )
        StoryProgressFactory(
            story=own, character_sheet=self.ravenna.sheet_data, current_episode=episode
        )
        self.assertIn(
            "Beat marked Success.", self.telnet(self.ravenna, f"story mark {beat.pk} success")
        )
        self.assertFalse(self.rewarded(self.ravenna))

    def test_a_group_story_advances_one_table_at_a_time(self) -> None:
        group = StoryFactory(
            title="The Guild's Wager",
            scope=StoryScope.GROUP,
            primary_table=self.table,
            owners=[self.ravenna.db_account],
        )
        chapter = ChapterFactory(story=group, title="Stakes", order=1, is_active=True)
        opening = EpisodeFactory(chapter=chapter, title="The Opening Bid", order=1, is_active=True)
        closing = EpisodeFactory(chapter=chapter, title="The Closing Bid", order=2)
        TransitionFactory(source_episode=opening, target_episode=closing)
        ours = GroupStoryProgressFactory(story=group, gm_table=self.table, current_episode=opening)
        theirs = GroupStoryProgressFactory(
            story=group, gm_table=GMTableFactory(gm=GMProfileFactory()), current_episode=opening
        )
        self.assertIn(
            "Episode 'The Opening Bid' resolved.",
            self.telnet(self.ravenna, f"story resolve {opening.pk}"),
        )
        ours.refresh_from_db()
        theirs.refresh_from_db()
        advanced = [p for p in (ours, theirs) if p.current_episode_id == closing.pk]
        self.assertEqual(len(advanced), 1)


class CallingTheCanon(_StoryTable):
    def test_the_gm_raises_the_stakes_and_then_steps_away(self) -> None:
        told = self.telnet(self.ravenna, f"story review-status {self.story.pk}")
        self.assertIn("Impact tier: table (effective: table)", told)
        self.assertIn("Canon review: none requested", told)
        self.assertIn(
            "You do not own or lead this story.",
            self.telnet(self.hobb, f"story review-status {self.story.pk}"),
        )
        self.assertIn(
            "Usage: story impact <story-id>=<table|regional|world>",
            self.telnet(self.ravenna, f"story impact {self.story.pk}=cosmic"),
        )

        told = self.telnet(self.ravenna, f"story impact {self.story.pk}=regional")
        self.assertIn("Impact tier set to regional for The Lantern Debt.", told)
        self.assertIn("Canon review requested; awaiting staff clearance.", told)
        told = self.telnet(self.ravenna, f"story review-status {self.story.pk}")
        self.assertIn("Impact tier: regional", told)
        self.assertIn("Canon review: Pending", told)

        # Staff work the queue. Marrow sends it back once, then clears the raised tier.
        marrow = self.make_player("Marrow", room=self.lantern)
        marrow.db_account.permissions.add("Admin")
        review = CanonReview.objects.get(story=self.story)
        self.assertIn(
            f"Pending canon reviews:\n  [{review.pk}] The Lantern Debt — tier regional "
            "(status pending)",
            self.telnet(marrow, "canonreview list"),
        )
        self.assertIn(
            "Usage: canonreview changes <id> notes=<text>",
            self.telnet(marrow, f"canonreview changes {review.pk}"),
        )
        self.assertIn("No canon review #999999.", self.telnet(marrow, "canonreview clear 999999"))
        self.assertIn(
            f"Canon review #{review.pk} returned with changes for The Lantern Debt.",
            self.telnet(marrow, f"canonreview changes {review.pk} notes=Narrow the scope"),
        )
        review.refresh_from_db()
        self.assertEqual(review.status, CanonReviewStatus.CHANGES_REQUESTED)
        told = self.telnet(self.ravenna, f"story review-status {self.story.pk}")
        self.assertIn("Canon review: Changes requested", told)
        self.assertIn("Notes: Narrow the scope", told)

        told = self.telnet(self.ravenna, f"story impact {self.story.pk}=world")
        self.assertIn("Impact tier set to world for The Lantern Debt.", told)
        self.assertIn("Canon review requested; awaiting staff clearance.", told)
        second = CanonReview.objects.get(story=self.story, status=CanonReviewStatus.PENDING)
        self.assertIn(
            f"Canon review #{second.pk} cleared for The Lantern Debt.",
            self.telnet(marrow, f"canonreview clear {second.pk} notes=Fine by me"),
        )
        self.assertIn("No pending canon reviews.", self.telnet(marrow, "canonreview list"))
        self.assertIn(
            "Canon review: CLEARED",
            self.telnet(self.ravenna, f"story review-status {self.story.pk}"),
        )
        self.assertIn(
            "This story's impact tier is frozen; it has a cleared canon review.",
            self.telnet(self.ravenna, f"story impact {self.story.pk}=table"),
        )

        # An experienced GM's regional tier clears itself; a table tier asks for no review.
        seed_default_gm_level_caps()
        GMProfileFactory(account=self.hobb.db_account, level=GMLevel.EXPERIENCED)
        ledger = StoryFactory(title="The Dock Ledger", owners=[self.hobb.db_account])
        self.assertIn(
            "Impact tier set to table for The Dock Ledger.",
            self.telnet(self.hobb, f"story impact {ledger.pk}=table"),
        )
        self.assertFalse(CanonReview.objects.filter(story=ledger).exists())
        told = self.telnet(self.hobb, f"story impact {ledger.pk}=regional")
        self.assertIn("Canon review auto-cleared by your GM level.", told)
        self.assertEqual(CanonReview.objects.get(story=ledger).status, CanonReviewStatus.CLEARED)

        told = self.telnet(self.ravenna, f"story surrender {self.story.pk}")
        self.assertIn("Surrendered oversight of The Lantern Debt. It is now seeking a GM.", told)
        self.story.refresh_from_db()
        self.assertIsNone(self.story.primary_table_id)
        self.assertIn(
            "You do not own or lead this story.",
            self.telnet(self.ravenna, f"story review-status {self.story.pk}"),
        )
        self.assertIn(
            "Usage: story surrender <story-id>", self.telnet(self.ravenna, "story surrender")
        )


class OpeningASceneRoom(JourneyCase):
    """Ravenna spins up a scene room, lets Ysmay in, and closes it with her inside."""

    def setUp(self) -> None:
        super().setUp()
        GMLevelCapFactory()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.ravenna = self.make_player("Ravenna", room=self.lantern)
        self.gm_profile = GMProfileFactory(account=self.ravenna.db_account)

    def test_a_room_is_spun_up_entered_left_and_closed(self) -> None:
        self.assertIn(
            "GM trust required.", self.telnet(self.hobb, "sceneroom The Old Mill = A ruined mill.")
        )
        self.assertIn("Usage: sceneroom", self.telnet(self.ravenna, "sceneroom"))

        told = self.telnet(self.ravenna, "sceneroom The Old Mill = A ruined mill, long abandoned.")
        instance = InstancedRoom.objects.get(gm_owner=self.gm_profile)
        mill = instance.room.objectdb
        mill_id = mill.pk  # closing the room deletes it, and a deleted row's pk reads None
        self.assertIn(f"The Old Mill spun up (#{instance.room.pk}); grant characters access.", told)

        self.assertIn("You have no story room grants.", self.telnet(self.ysmay, "joinroom"))
        self.assertIn(
            "You have no invitation to that room.", self.telnet(self.ysmay, f"joinroom {mill.pk}")
        )
        self.assertIn(
            "No such room among your grants. (joinroom to see them.)",
            self.telnet(self.ysmay, "joinroom Nowhere"),
        )

        result = self.web(self.ravenna, "grant_story_room", room_id=mill.pk, character_name="Ysmay")
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, "Ysmay may now join The Old Mill.")

        self.assertIn(
            f"Rooms you may join:\n  #{mill.pk} The Old Mill", self.telnet(self.ysmay, "joinroom")
        )
        self.assertIn("You join The Old Mill.", self.telnet(self.ysmay, "joinroom The Old Mill"))
        self.ysmay.refresh_from_db()
        self.assertEqual(self.ysmay.location, mill)
        self.assertIn("You leave.", self.telnet(self.ysmay, "leaveroom"))
        self.assertEqual(self.ysmay.location, self.lantern)
        self.assertIn("You're not in a story room.", self.telnet(self.ysmay, "leaveroom"))

        # Two grants sharing a name: the lower room id wins, every time.
        self.telnet(self.ravenna, "sceneroom The Old Mill = The other mill, across the stream.")
        twin = InstancedRoom.objects.exclude(pk=instance.pk).get(gm_owner=self.gm_profile)
        self.web(self.ravenna, "grant_story_room", room_id=twin.room.pk, character_name="Ysmay")
        self.assertIn("You join The Old Mill.", self.telnet(self.ysmay, "joinroom The Old Mill"))
        self.assertEqual(self.ysmay.location.pk, min(mill.pk, twin.room.pk))
        self.assertIn("You leave.", self.telnet(self.ysmay, "leaveroom"))
        self.assertIn("Usage: sceneroom", self.telnet(self.ravenna, "sceneroom close x"))

        self.assertIn("You join The Old Mill.", self.telnet(self.ysmay, f"joinroom #{mill.pk}"))
        self.assertIn("GM trust required.", self.telnet(self.hobb, f"sceneroom close {mill.pk}"))
        self.assertIn("Scene room closed.", self.telnet(self.ravenna, f"sceneroom close {mill.pk}"))
        self.assertEqual(self.ysmay.location, self.lantern)
        self.assertIn("No such room.", self.telnet(self.ravenna, f"sceneroom close {mill_id}"))
