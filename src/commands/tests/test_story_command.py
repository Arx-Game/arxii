"""Tests for the ``story`` GM telnet namespace command (#1495)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.types import ActionResult
from commands.story import CmdStory
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.stories.constants import StoryScope
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
)


def _make_cmd(caller, args: str) -> CmdStory:
    """Build a CmdStory with the given caller and args."""
    cmd = CmdStory()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"story {args}".strip()
    return cmd


def _messages(caller: MagicMock) -> list[str]:
    """Return all positional string messages sent to *caller*.msg."""
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class CmdStoryRoutingTests(TestCase):
    """Usage and unknown subcommand handling."""

    def setUp(self) -> None:
        self.account = AccountFactory()
        self.caller = MagicMock()
        self.caller.msg = MagicMock()
        self.caller.account = self.account

    def _run(self, args: str) -> list[str]:
        cmd = _make_cmd(self.caller, args)
        cmd.func()
        return _messages(self.caller)

    def test_bare_command_with_no_stories_says_so(self) -> None:
        messages = self._run("")
        self.assertTrue(
            any("no active stories" in m.lower() for m in messages),
            f"Expected 'no active stories' message; got {messages}",
        )

    def test_unknown_subverb_shows_usage(self) -> None:
        messages = self._run("frobnicate")
        self.assertTrue(
            any("Usage" in m for m in messages),
            f"Expected usage message; got {messages}",
        )


class CmdStorySubverbTests(TestCase):
    """Each subverb routes to the correct action with parsed kwargs."""

    def setUp(self) -> None:
        self.caller = MagicMock()
        self.caller.msg = MagicMock()

        # Objects referenced by numeric id in the routing tests.  Pks are left
        # to the database so the test stays valid regardless of Postgres sequence
        # state; each test reads the generated pk from these attributes.
        self.story = StoryFactory(title="Mock Story")
        self.chapter = ChapterFactory(story=self.story)
        self.episode = EpisodeFactory(title="Mock Episode", chapter=self.chapter)
        self.promote_episode = EpisodeFactory(title="Promote Episode", chapter=self.chapter)
        self.beat = BeatFactory(episode=self.episode)

    def _run(self, args: str) -> list[str]:
        cmd = _make_cmd(self.caller, args)
        cmd.func()
        return _messages(self.caller)

    @patch("actions.definitions.gm_stories.CompleteStoryAction.run")
    def test_complete_dispatches_story_id(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Story completed.")
        story_id = str(self.story.pk)
        messages = self._run(f"complete {story_id}")
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["story_id"], story_id)
        self.assertIn("Story completed.", messages)

    def test_complete_requires_story_id(self) -> None:
        messages = self._run("complete")
        self.assertTrue(
            any("Usage" in m or "story" in m.lower() for m in messages),
            f"Expected usage error; got {messages}",
        )

    @patch("actions.definitions.gm_stories.ResolveEpisodeAction.run")
    def test_resolve_episode_only(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Episode resolved.")
        episode_id = str(self.episode.pk)
        messages = self._run(f"resolve {episode_id}")
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["episode_id"], episode_id)
        self.assertNotIn("chosen_transition_id", kwargs)
        self.assertIn("Episode resolved.", messages)

    @patch("actions.definitions.gm_stories.ResolveEpisodeAction.run")
    def test_resolve_with_numeric_transition(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Episode resolved.")
        episode_id = str(self.episode.pk)
        self._run(f"resolve {episode_id} 5")
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["episode_id"], episode_id)
        self.assertEqual(kwargs["chosen_transition_id"], "5")

    @patch("actions.definitions.gm_stories.ResolveEpisodeAction.run")
    def test_resolve_with_notes(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Episode resolved.")
        episode_id = str(self.episode.pk)
        self._run(f"resolve {episode_id} final confrontation")
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["episode_id"], episode_id)
        self.assertNotIn("chosen_transition_id", kwargs)
        self.assertEqual(kwargs["gm_notes"], "final confrontation")

    @patch("actions.definitions.gm_stories.ResolveEpisodeAction.run")
    def test_resolve_with_transition_and_notes(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Episode resolved.")
        episode_id = str(self.episode.pk)
        self._run(f"resolve {episode_id} 5 final confrontation")
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["episode_id"], episode_id)
        self.assertEqual(kwargs["chosen_transition_id"], "5")
        self.assertEqual(kwargs["gm_notes"], "final confrontation")

    def test_resolve_requires_episode_id(self) -> None:
        messages = self._run("resolve")
        self.assertTrue(
            any("Usage" in m or "episode" in m.lower() for m in messages),
            f"Expected usage error; got {messages}",
        )

    @patch("actions.definitions.gm_stories.PromoteEpisodeAction.run")
    def test_promote_dispatches_episode_and_target(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Promoted.")
        episode_id = str(self.promote_episode.pk)
        messages = self._run(f"promote {episode_id} plot")
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["episode_id"], episode_id)
        self.assertEqual(kwargs["target"], "plot")
        self.assertIn("Promoted.", messages)

    def test_promote_requires_episode_and_target(self) -> None:
        messages = self._run("promote")
        self.assertTrue(
            any("Usage" in m for m in messages),
            f"Expected usage error; got {messages}",
        )

    @patch("actions.definitions.gm_stories.MarkBeatAction.run")
    def test_mark_dispatches_beat_outcome_and_notes(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Beat marked.")
        beat_id = str(self.beat.pk)
        messages = self._run(f"mark {beat_id} success the heroes won")
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["beat_id"], beat_id)
        self.assertEqual(kwargs["outcome"], "success")
        self.assertEqual(kwargs["gm_notes"], "the heroes won")
        self.assertIn("Beat marked.", messages)

    @patch("actions.definitions.gm_stories.MarkBeatAction.run")
    def test_mark_without_notes(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Beat marked.")
        beat_id = str(self.beat.pk)
        self._run(f"mark {beat_id} failure")
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["beat_id"], beat_id)
        self.assertEqual(kwargs["outcome"], "failure")
        self.assertEqual(kwargs.get("gm_notes", ""), "")

    def test_mark_requires_beat_and_outcome(self) -> None:
        messages = self._run("mark")
        self.assertTrue(
            any("Usage" in m for m in messages),
            f"Expected usage error; got {messages}",
        )


class CmdStoryPermissionDenialTests(TestCase):
    """Permission-denial results from the action surface to the caller."""

    def setUp(self) -> None:
        self.caller = MagicMock()
        self.caller.msg = MagicMock()
        self.story = StoryFactory(title="Mock Story")

    @patch("actions.definitions.gm_stories.CompleteStoryAction.run")
    def test_denial_message_surfaces(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(
            success=False,
            message="Only the story's Lead GM or staff may do that.",
        )
        cmd = _make_cmd(self.caller, f"complete {self.story.pk}")
        cmd.func()
        messages = _messages(self.caller)
        self.assertIn("Only the story's Lead GM or staff may do that.", messages)


class CmdStoryResolutionTests(TestCase):
    """Identifier resolution can use pk or case-insensitive title."""

    def setUp(self) -> None:
        self.caller = MagicMock()
        self.caller.msg = MagicMock()

    def _run(self, args: str) -> list[str]:
        cmd = _make_cmd(self.caller, args)
        cmd.func()
        return _messages(self.caller)

    @patch("actions.definitions.gm_stories.CompleteStoryAction.run")
    def test_complete_resolves_story_by_title(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Story completed.")
        story = StoryFactory(title="Crimson")

        self._run("complete crimson")

        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["story_id"], str(story.pk))

    @patch("actions.definitions.gm_stories.ResolveEpisodeAction.run")
    def test_resolve_resolves_episode_by_title(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Episode resolved.")
        episode = EpisodeFactory(title="Spire")

        self._run("resolve spire")

        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["episode_id"], str(episode.pk))

    @patch("actions.definitions.gm_stories.PromoteEpisodeAction.run")
    def test_promote_resolves_episode_by_title(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Promoted.")
        episode = EpisodeFactory(title="Whispers")

        self._run("promote whispers plot")

        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["episode_id"], str(episode.pk))
        self.assertEqual(kwargs["target"], "plot")

    def test_mark_rejects_non_numeric_beat_id(self) -> None:
        messages = self._run("mark abc success")
        self.assertTrue(
            any("numeric" in m.lower() for m in messages),
            f"Expected numeric-beat error; got {messages}",
        )


class CmdStoryPlayerListTests(TestCase):
    """Bare `story` / `story list` — the caller's own active stories (#1853)."""

    def setUp(self) -> None:
        self.account = AccountFactory()
        self.char = CharacterFactory()
        self.char.db_account = self.account
        self.char.save()
        self.sheet = CharacterSheetFactory(character=self.char)

        self.caller = MagicMock()
        self.caller.msg = MagicMock()
        self.caller.account = self.account

    def _run(self, args: str) -> list[str]:
        cmd = _make_cmd(self.caller, args)
        cmd.func()
        return _messages(self.caller)

    def test_bare_story_with_no_active_stories(self) -> None:
        messages = self._run("")
        joined = " ".join(messages)
        self.assertIn("no active stories", joined.lower())

    def test_bare_story_lists_active_character_story(self) -> None:
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=self.sheet)
        StoryProgressFactory(story=story, character_sheet=self.sheet, current_episode=None)

        messages = self._run("")

        joined = " ".join(messages)
        self.assertIn(story.title, joined)

    def test_story_list_is_an_explicit_alias_for_bare(self) -> None:
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=self.sheet)
        StoryProgressFactory(story=story, character_sheet=self.sheet, current_episode=None)

        messages = self._run("list")

        joined = " ".join(messages)
        self.assertIn(story.title, joined)


class CmdStoryPlayerBeatsTests(TestCase):
    """`story beats <episode-id>` — beats in one of the caller's active episodes (#1853)."""

    def setUp(self) -> None:
        from evennia_extensions.factories import AccountFactory, CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.stories.factories import (
            ChapterFactory,
            EpisodeFactory,
            StoryFactory,
            StoryProgressFactory,
        )

        self.account = AccountFactory()
        self.char = CharacterFactory()
        self.char.db_account = self.account
        self.char.save()
        self.sheet = CharacterSheetFactory(character=self.char)

        self.story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=self.sheet)
        self.chapter = ChapterFactory(story=self.story, order=1)
        self.episode = EpisodeFactory(chapter=self.chapter, order=1)
        StoryProgressFactory(
            story=self.story, character_sheet=self.sheet, current_episode=self.episode
        )

        self.caller = MagicMock()
        self.caller.msg = MagicMock()
        self.caller.account = self.account

    def _run(self, args: str) -> list[str]:
        cmd = _make_cmd(self.caller, args)
        cmd.func()
        return _messages(self.caller)

    def test_beats_requires_episode_id(self) -> None:
        messages = self._run("beats")
        self.assertTrue(any("Usage" in m for m in messages))

    def test_beats_rejects_episode_not_in_an_active_story_of_the_caller(self) -> None:
        from world.stories.factories import EpisodeFactory

        other_episode = EpisodeFactory(chapter=self.chapter, order=2)
        messages = self._run(f"beats {other_episode.pk}")
        joined = " ".join(messages)
        self.assertIn("not one of your active stories", joined.lower())

    def test_beats_lists_visible_beat_with_player_hint(self) -> None:
        from world.stories.factories import BeatFactory

        BeatFactory(episode=self.episode, player_hint="A stranger arrives.")
        messages = self._run(f"beats {self.episode.pk}")
        joined = " ".join(messages)
        self.assertIn("A stranger arrives.", joined)

    def test_beats_hides_secret_beat_with_no_hint(self) -> None:
        from world.stories.constants import BeatVisibility
        from world.stories.factories import BeatFactory

        BeatFactory(episode=self.episode, player_hint="", visibility=BeatVisibility.SECRET)
        messages = self._run(f"beats {self.episode.pk}")
        joined = " ".join(messages)
        self.assertIn("(Hidden Beat)", joined)

    def test_beats_flags_pending_signoff(self) -> None:
        from world.boundaries.factories import TreasuredSubjectFactory
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )
        from world.stories.constants import StakeSubjectKind
        from world.stories.factories import BeatFactory, StakeFactory

        beat = BeatFactory(episode=self.episode, player_hint="A duel is proposed.")
        entry = RosterEntryFactory(character_sheet=self.sheet)
        player_data = PlayerDataFactory(account=self.account)
        tenure = RosterTenureFactory(roster_entry=entry, player_data=player_data)
        TreasuredSubjectFactory(
            owner=tenure,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Signet Ring",
        )
        StakeFactory(
            beat=beat,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Signet Ring",
        )

        messages = self._run(f"beats {self.episode.pk}")

        joined = " ".join(messages)
        self.assertIn("SIGN-OFF NEEDED", joined)
        self.assertIn("Signet Ring", joined)
