"""Speaker queue telnet command — the ``line`` namespace (#2356).

Bare ``line`` shows the current queue. Subverbs dispatch to the matching
Action via ``action.run()`` — the same seam the web ViewSet uses.
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand

_USAGE = (
    "Usage: line <subcommand>\n"
    "  line                      — show the queue\n"
    "  line open                 — open a speaker queue in this room\n"
    "  line close                — close the queue\n"
    "  line join                 — get in line\n"
    "  line leave                — leave the queue\n"
    "  line next                 — yield your turn (advance)\n"
    "  line skip <name>          — skip a specific persona (AFK escape)\n"
    "  line status               — same as bare 'line'"
)


class CmdLine(ArxCommand):
    """Manage a speaker queue in your current room.

    Usage:
        line
        line open
        line close
        line join
        line leave
        line next
        line skip <name>
    """

    key = "line"
    locks = "cmd:all()"
    action = None  # Routing is done in func().

    def func(self) -> None:
        raw = (self.args or "").strip()
        if not raw:
            self._show_queue()
            return
        parts = raw.split(maxsplit=1)
        subverb = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        handler = {
            "status": lambda: self._show_queue(),
            "open": lambda: self._dispatch("open"),
            "close": lambda: self._dispatch("close"),
            "join": lambda: self._dispatch("join"),
            "leave": lambda: self._dispatch("leave"),
            "next": lambda: self._dispatch("advance"),
            "skip": lambda: self._dispatch("skip", target_name=rest),
        }.get(subverb)

        if handler is None:
            self.msg(_USAGE)
            return
        handler()

    def _dispatch(self, action_key: str, **kwargs: Any) -> None:
        """Dispatch to the matching Action."""
        from actions.definitions.speaker_queue import (  # noqa: PLC0415
            AdvanceSpeakerQueueAction,
            CloseSpeakerQueueAction,
            JoinSpeakerQueueAction,
            LeaveSpeakerQueueAction,
            OpenSpeakerQueueAction,
            SkipSpeakerAction,
        )

        actions = {
            "open": OpenSpeakerQueueAction,
            "close": CloseSpeakerQueueAction,
            "join": JoinSpeakerQueueAction,
            "leave": LeaveSpeakerQueueAction,
            "advance": AdvanceSpeakerQueueAction,
            "skip": SkipSpeakerAction,
        }
        action_cls = actions[action_key]
        result = action_cls().run(actor=self.caller, **kwargs)
        if result.message:
            self.msg(result.message)

    def _show_queue(self) -> None:
        """Display the current speaker queue for the caller's room."""
        from world.scenes.speaker_queue_services import (  # noqa: PLC0415
            get_active_queue,
            queue_entries,
        )

        room = self.caller.location
        if room is None:
            self.msg("You are not in a room.")
            return

        queue = get_active_queue(room)
        if queue is None:
            self.msg("There is no active speaker queue here. Use 'line open' to start one.")
            return

        entries = list(queue_entries(queue))
        if not entries:
            self.msg("The speaker queue is open but empty. Use 'line join' to get in line.")
            return

        lines = ["Speaker queue:"]
        for entry in entries:
            marker = " >" if entry.position == 1 else f"  {entry.position}."
            lines.append(f"{marker} {entry.persona.name}")
        lines.append("")
        lines.append("Use 'line join' to get in line, 'line next' to advance.")
        self.msg("\n".join(lines))
