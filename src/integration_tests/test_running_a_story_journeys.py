"""Journeys for the stories tranche (#3657, tranche 4, step 1): a player reading her
own story while her Lead GM runs it beat by beat, the GM calling the canon on a
story's impact, and a GM opening a scene room for her players. Each types what a
player types or sends what the web client sends, and asserts what the player and
the GM were told."""

from __future__ import annotations

from integration_tests.harness import JourneyCase
from world.gm.factories import GMLevelCapFactory, GMProfileFactory, GMTableFactory
from world.instances.models import InstancedRoom
from world.narrative.models import NarrativeMessageDelivery
from world.stories.constants import BeatOutcome, StoryMaturity, StoryScope
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
)
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

        told = self.telnet(self.ysmay, f"story beats {self.first.pk}")
        self.assertIn(f"Beats:\n  [{self.beat.pk}] Find out who knocked (unsatisfied)", told)
        self.assertIn(
            "That's not one of your active stories.",
            self.telnet(self.ysmay, f"story beats {self.second.pk}"),
        )
        self.assertIn(
            "An episode must be specified by its numeric ID.",
            self.telnet(self.ysmay, "story beats first"),
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

        told = self.telnet(self.ravenna, f"story resolve {self.first.pk} The door swings open.")
        self.assertIn("Episode 'The First Knock' resolved.", told)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.current_episode_id, self.second.pk)
        self.assertIn('currently in "The Second Knock"', self.telnet(self.ysmay, "story"))
        self.assertIn(
            "Only the story's Lead GM or staff may do that.",
            self.telnet(self.hobb, f"story resolve {self.second.pk}"),
        )

        told = self.telnet(self.ravenna, f"story complete {self.story.pk}")
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

        self.assertIn("You join The Old Mill.", self.telnet(self.ysmay, f"joinroom #{mill.pk}"))
        self.assertIn("GM trust required.", self.telnet(self.hobb, f"sceneroom close {mill.pk}"))
        self.assertIn("Scene room closed.", self.telnet(self.ravenna, f"sceneroom close {mill.pk}"))
        self.assertEqual(self.ysmay.location, self.lantern)
        self.assertIn("No such room.", self.telnet(self.ravenna, f"sceneroom close {mill_id}"))
