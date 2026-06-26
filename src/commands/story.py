"""GM story lifecycle telnet namespace (#1495).

A thin command face for the four story actions in ``actions.definitions.gm_stories``.
Each subverb delegates directly to ``Action().run(actor=self.caller, **kwargs)``.
No business logic lives here.
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand
from commands.exceptions import CommandError

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
_TRANSITION_INDEX = 1

_SUBVERB_HANDLERS: dict[str, str] = {
    "complete": "_handle_complete",
    "resolve": "_handle_resolve",
    "promote": "_handle_promote",
    "mark": "_handle_mark",
}


class CmdStory(ArxCommand):
    """Manage story episodes and beats.

    All subcommands are gated by the story's Lead GM or staff status in the
    backing action layer.
    """

    key = "story"
    aliases = ()
    locks = "cmd:all()"
    action = None  # Routed manually by subverb.

    def func(self) -> None:
        """Route the leading subverb to the appropriate action."""
        raw = (self.args or "").strip()
        if not raw:
            self.msg(_USAGE)
            return

        parts = raw.split(maxsplit=1)
        subverb = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        handler_name = _SUBVERB_HANDLERS.get(subverb)
        if handler_name is None:
            self.msg(_USAGE)
            return

        try:
            getattr(self, handler_name)(rest)
        except CommandError as err:
            self.msg(str(err))

    def _run_action(self, action_cls: type[Any], **kwargs: Any) -> None:
        """Instantiate *action_cls* and forward the result message."""
        result = action_cls().run(actor=self.caller, **kwargs)
        if result.message:
            self.msg(result.message)

    def _require_arg(self, value: str, usage: str) -> str:
        """Return a stripped token or raise CommandError with *usage*."""
        token = value.strip()
        if not token:
            msg = usage
            raise CommandError(msg)
        return token

    def _handle_complete(self, rest: str) -> None:
        """Parse ``complete <story-id>`` and dispatch CompleteStoryAction."""
        from actions.definitions.gm_stories import CompleteStoryAction  # noqa: PLC0415

        story_id = self._require_arg(rest, _COMPLETE_USAGE)
        self._run_action(CompleteStoryAction, story_id=story_id.split()[0])

    def _handle_resolve(self, rest: str) -> None:
        """Parse ``resolve <episode-id> [transition-id] [notes]`` and dispatch ResolveEpisodeAction.

        If the token after the episode id is numeric, it is treated as a
        transition id; all remaining tokens become GM notes.
        """
        from actions.definitions.gm_stories import ResolveEpisodeAction  # noqa: PLC0415

        tokens = rest.split()
        if not tokens:
            msg = _RESOLVE_USAGE
            raise CommandError(msg)

        kwargs: dict[str, object] = {"episode_id": tokens[0]}
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

        self._run_action(
            PromoteEpisodeAction,
            episode_id=tokens[0],
            target=tokens[1].lower(),
        )

    def _handle_mark(self, rest: str) -> None:
        """Parse ``mark <beat-id> <outcome> [notes]`` and dispatch MarkBeatAction."""
        from actions.definitions.gm_stories import MarkBeatAction  # noqa: PLC0415

        tokens = rest.split()
        if len(tokens) < _MIN_MARK_TOKENS:
            msg = _MARK_USAGE
            raise CommandError(msg)

        beat_id = tokens[0]
        outcome = tokens[1].lower()
        gm_notes = " ".join(tokens[_MIN_MARK_TOKENS:]).strip()

        kwargs: dict[str, object] = {"beat_id": beat_id, "outcome": outcome}
        if gm_notes:
            kwargs["gm_notes"] = gm_notes

        self._run_action(MarkBeatAction, **kwargs)
