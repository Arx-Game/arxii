"""Tests for the ``story`` GM telnet namespace command (#1495)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.types import ActionResult
from commands.story import CmdStory
from world.stories.factories import (
    BeatFactory,
    EpisodeFactory,
    StoryFactory,
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
        self.caller = MagicMock()
        self.caller.msg = MagicMock()

    def _run(self, args: str) -> list[str]:
        cmd = _make_cmd(self.caller, args)
        cmd.func()
        return _messages(self.caller)

    def test_bare_command_shows_usage(self) -> None:
        messages = self._run("")
        self.assertTrue(
            any("Usage" in m for m in messages),
            f"Expected usage message; got {messages}",
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

        # Numeric ids referenced by the routing tests must exist so the
        # command layer can resolve them before dispatching.
        StoryFactory(pk=42, title="Mock Story")
        EpisodeFactory(pk=12, title="Mock Episode")
        EpisodeFactory(pk=7, title="Promote Episode")
        BeatFactory(pk=8)

    def _run(self, args: str) -> list[str]:
        cmd = _make_cmd(self.caller, args)
        cmd.func()
        return _messages(self.caller)

    @patch("actions.definitions.gm_stories.CompleteStoryAction.run")
    def test_complete_dispatches_story_id(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Story completed.")
        messages = self._run("complete 42")
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["story_id"], "42")
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
        messages = self._run("resolve 12")
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["episode_id"], "12")
        self.assertNotIn("chosen_transition_id", kwargs)
        self.assertIn("Episode resolved.", messages)

    @patch("actions.definitions.gm_stories.ResolveEpisodeAction.run")
    def test_resolve_with_numeric_transition(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Episode resolved.")
        self._run("resolve 12 5")
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["episode_id"], "12")
        self.assertEqual(kwargs["chosen_transition_id"], "5")

    @patch("actions.definitions.gm_stories.ResolveEpisodeAction.run")
    def test_resolve_with_notes(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Episode resolved.")
        self._run("resolve 12 final confrontation")
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["episode_id"], "12")
        self.assertNotIn("chosen_transition_id", kwargs)
        self.assertEqual(kwargs["gm_notes"], "final confrontation")

    @patch("actions.definitions.gm_stories.ResolveEpisodeAction.run")
    def test_resolve_with_transition_and_notes(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Episode resolved.")
        self._run("resolve 12 5 final confrontation")
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["episode_id"], "12")
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
        messages = self._run("promote 7 plot")
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["episode_id"], "7")
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
        messages = self._run("mark 8 success the heroes won")
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["actor"], self.caller)
        self.assertEqual(kwargs["beat_id"], "8")
        self.assertEqual(kwargs["outcome"], "success")
        self.assertEqual(kwargs["gm_notes"], "the heroes won")
        self.assertIn("Beat marked.", messages)

    @patch("actions.definitions.gm_stories.MarkBeatAction.run")
    def test_mark_without_notes(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(success=True, message="Beat marked.")
        self._run("mark 8 failure")
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["beat_id"], "8")
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
        StoryFactory(pk=42, title="Mock Story")

    @patch("actions.definitions.gm_stories.CompleteStoryAction.run")
    def test_denial_message_surfaces(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ActionResult(
            success=False,
            message="Only the story's Lead GM or staff may do that.",
        )
        cmd = _make_cmd(self.caller, "complete 42")
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
