"""GM story lifecycle telnet namespace (#1495).

A thin command face for the four story actions in ``actions.definitions.gm_stories``.
Each subverb delegates directly to ``Action().run(actor=self.caller, **kwargs)``.
No business logic lives here.
"""

from __future__ import annotations

from commands.exceptions import CommandError
from commands.namespace import ArxNamespaceCommand
from commands.utils.gm_resolution import (
    resolve_episode_or_error,
    resolve_numeric_beat_id_or_error,
    resolve_story_or_error,
)

_USAGE = (
    "Usage: story <subcommand>\n"
    "  story complete <story-id>\n"
    "  story resolve <episode-id> [transition-id] [notes]\n"
    "  story promote <episode-id> <pitch|outline|plot>\n"
    "  story mark <beat-id> <success|failure> [notes]"
)

_COMPLETE_USAGE = "Usage: story complete <story-id>"
_RESOLVE_USAGE = "Usage: story resolve <episode-id> [transition-id] [notes]"
_PROMOTE_USAGE = "Usage: story promote <episode-id> <pitch|outline|plot>"
_MARK_USAGE = "Usage: story mark <beat-id> <success|failure> [notes]"

_MIN_PROMOTE_TOKENS = 2
_MIN_MARK_TOKENS = 2

_SUBVERB_HANDLERS: dict[str, str] = {
    "complete": "_handle_complete",
    "resolve": "_handle_resolve",
    "promote": "_handle_promote",
    "mark": "_handle_mark",
}


class CmdStory(ArxNamespaceCommand):
    """Manage story episodes and beats.

    All subcommands are gated by the story's Lead GM or staff status in the
    backing action layer.
    """

    key = "story"
    aliases = ()
    locks = "cmd:all()"
    _USAGE = _USAGE
    _SUBVERB_HANDLERS = _SUBVERB_HANDLERS

    def _handle_complete(self, rest: str) -> None:
        """Parse ``complete <story-id>`` and dispatch CompleteStoryAction."""
        from actions.definitions.gm_stories import CompleteStoryAction  # noqa: PLC0415

        story_id = self._require_arg(rest, _COMPLETE_USAGE)
        story = resolve_story_or_error(story_id)
        self._run_action(CompleteStoryAction, story_id=str(story.pk))

    def _handle_resolve(self, rest: str) -> None:
        """Parse ``resolve <episode-id> [transition-id] [notes]`` and dispatch ResolveEpisodeAction.

        ``Transition`` has no name/title field, so it can only be supplied by
        numeric pk; any non-numeric second token is treated as the start of GM
        notes.
        """
        from actions.definitions.gm_stories import ResolveEpisodeAction  # noqa: PLC0415

        tokens = rest.split()
        if not tokens:
            msg = _RESOLVE_USAGE
            raise CommandError(msg)

        episode = resolve_episode_or_error(tokens[0])
        kwargs: dict[str, object] = {"episode_id": str(episode.pk)}
        remaining = tokens[1:]

        if remaining and remaining[0].isdigit():
            kwargs["chosen_transition_id"] = remaining[0]
            remaining = remaining[1:]

        gm_notes = " ".join(remaining).strip()
        if gm_notes:
            kwargs["gm_notes"] = gm_notes

        self._run_action(ResolveEpisodeAction, **kwargs)

    def _handle_promote(self, rest: str) -> None:
        """Parse ``promote <episode-id> <target>`` and dispatch PromoteEpisodeAction."""
        from actions.definitions.gm_stories import PromoteEpisodeAction  # noqa: PLC0415

        tokens = rest.split()
        if len(tokens) < _MIN_PROMOTE_TOKENS:
            msg = _PROMOTE_USAGE
            raise CommandError(msg)

        episode = resolve_episode_or_error(tokens[0])
        self._run_action(
            PromoteEpisodeAction,
            episode_id=str(episode.pk),
            target=tokens[1].lower(),
        )

    def _handle_mark(self, rest: str) -> None:
        """Parse ``mark <beat-id> <outcome> [notes]`` and dispatch MarkBeatAction."""
        from actions.definitions.gm_stories import MarkBeatAction  # noqa: PLC0415

        tokens = rest.split()
        if len(tokens) < _MIN_MARK_TOKENS:
            msg = _MARK_USAGE
            raise CommandError(msg)

        beat_id = resolve_numeric_beat_id_or_error(tokens[0])
        outcome = tokens[1].lower()
        gm_notes = " ".join(tokens[_MIN_MARK_TOKENS:]).strip()

        kwargs: dict[str, object] = {"beat_id": beat_id, "outcome": outcome}
        if gm_notes:
            kwargs["gm_notes"] = gm_notes

        self._run_action(MarkBeatAction, **kwargs)
