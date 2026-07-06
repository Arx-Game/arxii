"""Story telnet namespace: GM lifecycle actions + player self-service (#1495, #1853).

GM subverbs (complete/resolve/promote/mark) delegate directly to
``Action().run(actor=self.caller, **kwargs)`` and are gated by the story's
Lead GM or staff status in the backing action layer — unchanged from #1495.

Player subverbs (bare `story` / `list` / `beats` / `signoff`) are self-scoped
reads/mutations over the caller's own account — no GM/staff gate, mirroring
CmdGMTable's precedent of mixed permission tiers under one command namespace.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from commands.exceptions import CommandError
from commands.namespace import ArxNamespaceCommand
from commands.utils.gm_resolution import (
    resolve_episode_or_error,
    resolve_numeric_beat_id_or_error,
    resolve_story_or_error,
)

if TYPE_CHECKING:
    from world.boundaries.models import TreasuredSubject

_SignoffMatchT = TypeVar("_SignoffMatchT")

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
_MIN_SIGNOFF_TOKENS = 2  # beat-id + at least one subject token
_WITHDRAW_KEYWORD = "withdraw"

_SUBVERB_HANDLERS: dict[str, str] = {
    "complete": "_handle_complete",
    "resolve": "_handle_resolve",
    "promote": "_handle_promote",
    "mark": "_handle_mark",
    "list": "_handle_list",
    "beats": "_handle_beats",
    "signoff": "_handle_signoff",
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

    def _handle_beats(self, rest: str) -> None:
        """List a caller's-own-active-episode's beats, flagging pending sign-offs (#1853)."""
        from world.stories.constants import BeatVisibility  # noqa: PLC0415
        from world.stories.models import Beat  # noqa: PLC0415
        from world.stories.services.boundaries import (  # noqa: PLC0415
            player_pending_treasured_signoffs,
        )
        from world.stories.services.dashboards import active_stories_for_account  # noqa: PLC0415

        episode_id = self._require_arg(rest, "Usage: story beats <episode-id>.")
        if not episode_id.isdigit():
            msg = "An episode must be specified by its numeric ID."
            raise CommandError(msg)

        result = active_stories_for_account(self.caller.account)
        my_episode_ids = {
            entry["current_episode_id"]
            for entry in (
                *result["character_stories"],
                *result["group_stories"],
                *result["global_stories"],
            )
            if entry["current_episode_id"] is not None
        }
        if int(episode_id) not in my_episode_ids:
            msg = "That's not one of your active stories."
            raise CommandError(msg)

        beats = list(Beat.objects.filter(episode_id=episode_id).order_by("order"))
        if not beats:
            self.msg("No beats yet for that episode.")
            return

        player_data = getattr(self.caller.account, "player_data", None)  # noqa: GETATTR_LITERAL
        pending_by_beat: dict[int, tuple[int, ...]] = {}
        if player_data is not None:
            for entry in player_pending_treasured_signoffs(player_data, beats):
                pending_by_beat[entry.beat_id] = entry.treasured_subject_ids

        from world.boundaries.models import TreasuredSubject  # noqa: PLC0415

        pending_subject_ids = {tid for ids in pending_by_beat.values() for tid in ids}
        label_by_id = dict(
            TreasuredSubject.objects.filter(pk__in=pending_subject_ids).values_list(
                "pk", "subject_label"
            )
        )

        lines = ["Beats:"]
        for beat in beats:
            if beat.player_hint and beat.player_hint.strip():
                title = beat.player_hint
            elif beat.visibility == BeatVisibility.SECRET:
                title = "(Hidden Beat)"
            else:
                title = "Beat"
            outcome = beat.outcome or "unsatisfied"
            line = f"  [{beat.pk}] {title} ({outcome})"
            pending_ids = pending_by_beat.get(beat.pk, ())
            for tid in pending_ids:
                line += f"\n      SIGN-OFF NEEDED: {label_by_id.get(tid, '(unknown)')}"
            lines.append(line)
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

    def _handle_signoff(self, rest: str) -> None:
        """Grant or withdraw a treasured sign-off for a beat (#1853)."""
        from world.boundaries.models import TreasuredSubject  # noqa: PLC0415
        from world.stories.models import Beat, TreasuredSignoff  # noqa: PLC0415
        from world.stories.services.boundaries import (  # noqa: PLC0415
            grant_treasured_signoff,
            player_pending_treasured_signoffs,
            withdraw_treasured_signoff,
        )

        usage = "Usage: story signoff <beat-id> <subject> [withdraw]."
        tokens = rest.split()
        if len(tokens) < _MIN_SIGNOFF_TOKENS:
            raise CommandError(usage)

        beat_id = resolve_numeric_beat_id_or_error(tokens[0])
        try:
            beat = Beat.objects.get(pk=beat_id)
        except Beat.DoesNotExist as exc:
            msg = "No beat with that ID exists."
            raise CommandError(msg) from exc

        remaining = tokens[1:]
        withdraw = bool(remaining) and remaining[-1].lower() == _WITHDRAW_KEYWORD
        if withdraw:
            remaining = remaining[:-1]
        subject_token = " ".join(remaining).strip()
        if not subject_token:
            raise CommandError(usage)

        player_data = getattr(self.caller.account, "player_data", None)  # noqa: GETATTR_LITERAL
        if player_data is None:
            msg = "You have no player identity to sign off with."
            raise CommandError(msg)

        if withdraw:
            active_signoffs = TreasuredSignoff.objects.filter(
                beat=beat, player_data=player_data, withdrawn_at__isnull=True
            ).select_related("treasured_subject")
            signoff = self._match_subject_token(
                subject_token, [(s.treasured_subject, s) for s in active_signoffs]
            )
            if signoff is None:
                msg = f"No active sign-off for '{subject_token}' on beat {beat.pk}."
                raise CommandError(msg)
            withdraw_treasured_signoff(signoff)
            self.msg(f"Withdrawn: {signoff.treasured_subject.subject_label} on beat {beat.pk}.")
            return

        entries = player_pending_treasured_signoffs(player_data, [beat])
        pending_ids: tuple[int, ...] = entries[0].treasured_subject_ids if entries else ()
        candidates = list(TreasuredSubject.objects.filter(pk__in=pending_ids))
        subject = self._match_subject_token(subject_token, [(s, s) for s in candidates])
        if subject is None:
            msg = f"No pending sign-off for '{subject_token}' on beat {beat.pk}."
            raise CommandError(msg)
        grant_treasured_signoff(beat, player_data, subject)
        self.msg(f"Signed off: {subject.subject_label} on beat {beat.pk}.")

    @staticmethod
    def _match_subject_token(
        token: str,
        subject_and_result_pairs: list[tuple[TreasuredSubject, _SignoffMatchT]],
    ) -> _SignoffMatchT | None:
        """Match *token* (numeric pk or case-insensitive label) among the given
        (TreasuredSubject, result) pairs, returning the matching result or None."""
        if token.isdigit():
            token_id = int(token)
            for subject, result in subject_and_result_pairs:
                if subject.pk == token_id:
                    return result
            return None
        for subject, result in subject_and_result_pairs:
            if subject.subject_label.lower() == token.lower():
                return result
        return None
