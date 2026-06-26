"""E2E telnet journey: GM story lifecycle (#1495).

Drives the full story command path through mark, resolve, promote, and
complete, asserting both DB state and caller messages.

SQLite-compatible.
DbHolder trap: all Evennia ObjectDB instances live in setUp, never setUpTestData.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.story import CmdStory
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.stories.constants import (
    BeatOutcome,
    BeatPredicateType,
    StoryMaturity,
    StoryScope,
    TransitionMode,
)
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
)
from world.stories.models import BeatCompletion, EpisodeResolution
from world.stories.types import StoryStatus

_NOTIFY_BEAT_PATH = "world.stories.services.beats._notify_beat_completion"
_NOTIFY_EPISODE_PATH = "world.stories.services.narrative.notify_episode_resolution"


def _create_room():
    return ObjectDBFactory(
        db_key="StoryJourneyRoom",
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _create_actor_with_sheet(db_key: str, room=None, is_staff: bool = False):
    """Create a PC character in *room* with a live roster tenure.

    Returns (character, account, character_sheet).
    """
    account = AccountFactory(username=f"e2e_{db_key.lower()}", is_staff=is_staff)
    kwargs = {"db_key": db_key}
    if room is not None:
        kwargs["location"] = room
    char = CharacterFactory(**kwargs)
    sheet = CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(
        roster_entry=entry,
        player_data__account=account,
        end_date=None,
    )
    return char, account, sheet


def _run_cmd(caller, args: str) -> list[str]:
    """Invoke CmdStory with *args* and return all messages sent to caller."""
    caller.msg = MagicMock()
    cmd = CmdStory()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"story {args}".strip()
    cmd.func()
    return [str(call.args[0]) for call in caller.msg.call_args_list if call.args]


class StoryGMLifecycleE2ETest(TestCase):
    """Full telnet journey for the GM story lifecycle."""

    def setUp(self) -> None:
        # DbHolder trap: build all Evennia objects in setUp, never setUpTestData.
        self.room = _create_room()

        # Lead GM character (staff account so command actions succeed).
        self.gm_actor, self.gm_account, self.gm_sheet = _create_actor_with_sheet(
            "StoryLeadGM",
            room=self.room,
            is_staff=True,
        )

        # Story structure: story -> chapter -> episodes, with an auto transition.
        self.story = StoryFactory(
            owners=[self.gm_account],
            scope=StoryScope.CHARACTER,
            status=StoryStatus.ACTIVE,
            character_sheet=self.gm_sheet,
        )
        self.chapter = ChapterFactory(story=self.story, order=1, is_active=True)
        self.ep1 = EpisodeFactory(chapter=self.chapter, order=1, is_active=True)
        self.ep2 = EpisodeFactory(chapter=self.chapter, order=2)
        self.transition = TransitionFactory(
            source_episode=self.ep1,
            target_episode=self.ep2,
            mode=TransitionMode.AUTO,
        )

        # GM-marked beat on the first episode.
        self.beat = BeatFactory(
            episode=self.ep1,
            predicate_type=BeatPredicateType.GM_MARKED,
            agm_eligible=True,
        )

        # Active progress on the story.
        self.progress = StoryProgressFactory(
            story=self.story,
            character_sheet=self.gm_sheet,
            current_episode=self.ep1,
            is_active=True,
        )

        # A separate episode eligible for promotion to PLOT.
        self.promotable_ep = EpisodeFactory(
            chapter=self.chapter,
            order=3,
            maturity=StoryMaturity.OUTLINE,
            resting_conclusion="The threads draw tight.",
            is_ending=True,
        )

    def test_full_gm_story_lifecycle(self) -> None:
        """Run the story lifecycle through the telnet command seam."""
        # ---- Step 1: mark beat success ----------------------------------
        with patch(_NOTIFY_BEAT_PATH):
            msgs = _run_cmd(self.gm_actor, f"mark {self.beat.pk} success the heroes prevailed")
        self.assertIn("beat marked success", " ".join(msgs).lower())

        self.beat.refresh_from_db()
        self.assertEqual(self.beat.outcome, BeatOutcome.SUCCESS)
        self.assertTrue(
            BeatCompletion.objects.filter(beat=self.beat, outcome=BeatOutcome.SUCCESS).exists()
        )

        # ---- Step 2: resolve episode ------------------------------------
        with patch(_NOTIFY_EPISODE_PATH):
            msgs = _run_cmd(self.gm_actor, f"resolve {self.ep1.pk}")
        self.assertIn("episode '", " ".join(msgs).lower())
        self.assertIn("' resolved.", " ".join(msgs).lower())

        self.assertTrue(EpisodeResolution.objects.filter(episode=self.ep1).exists())
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.current_episode_id, self.ep2.pk)

        # ---- Step 3: promote episode to plot ---------------------------
        msgs = _run_cmd(self.gm_actor, f"promote {self.promotable_ep.pk} plot")
        self.assertIn("promoted to plot", " ".join(msgs).lower())

        self.promotable_ep.refresh_from_db()
        self.assertEqual(self.promotable_ep.maturity, StoryMaturity.PLOT)

        # ---- Step 4: complete story -------------------------------------
        msgs = _run_cmd(self.gm_actor, f"complete {self.story.pk}")
        self.assertIn("story '", " ".join(msgs).lower())
        self.assertIn("' completed.", " ".join(msgs).lower())

        self.story.refresh_from_db()
        self.assertEqual(self.story.status, StoryStatus.COMPLETED)
        self.assertIsNotNone(self.story.completed_at)
