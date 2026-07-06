"""Story telnet namespace: GM lifecycle actions + player self-service (#1495, #1853).

GM subverbs (complete/resolve/promote/mark) delegate directly to
``Action().run(actor=self.caller, **kwargs)`` and are gated by the story's
Lead GM or staff status in the backing action layer — unchanged from #1495.

Player subverbs (bare `story` / `list` / `beats` / `signoff`) are self-scoped
reads/mutations over the caller's own account — no GM/staff gate, mirroring
CmdGMTable's precedent of mixed permission tiers under one command namespace.
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
    "  story                              — your active stories\n"
    "  story list                         — same as bare `story`\n"
    "  story beats <episode-id>           — beats in one of your active episodes\n"
    "  story signoff <beat-id> <subject> [withdraw]\n"
    "                                     — grant/withdraw a treasured sign-off\n"
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
    "list": "_handle_list",
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

    def func(self) -> None:
        """Bare `story` is the player's active-stories listing; else route by subverb."""
        raw = (self.args or "").strip()
        if not raw:
            self._handle_list("")
            return
        super().func()

    def _handle_list(self, rest: str) -> None:
        """Show the caller's active stories across all three scopes (#1853)."""
        from world.stories.services.dashboards import active_stories_for_account  # noqa: PLC0415

        result = active_stories_for_account(self.caller.account)
        entries = [
            *result["character_stories"],
            *result["group_stories"],
            *result["global_stories"],
        ]
        if not entries:
            self.msg("You have no active stories.")
            return
        lines = ["Your active stories:"]
        for entry in entries:
            episode_bit = (
                f' — currently in "{entry["current_episode_title"]}"'
                if entry["current_episode_title"]
                else ""
            )
            lines.append(
                f"  [{entry['story_id']}] {entry['story_title']}{episode_bit} "
                f"({entry['status_label']})"
            )
        self.msg("\n".join(lines))

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
