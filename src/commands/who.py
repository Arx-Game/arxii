"""Telnet ``who`` command (#1463) — the online-presence roster.

A thin read over ``world.scenes.presence.who_listing``: currently-online characters by
active persona, with a **coarse** idle indicator (active / idle / away — never exact, so
identical idle times can't correlate an account's alts). The web frontend offers the same
data through the one service.
"""

from __future__ import annotations

from commands.command import ArxCommand


class CmdWho(ArxCommand):
    """See who is currently online.

    Lists online characters with a rough idle indicator (active / idle / away).

    Usage:
      who
    """

    key = "who"
    locks = "cmd:all()"
    help_category = "General"
    action = None

    def func(self) -> None:
        from world.scenes.presence import who_listing  # noqa: PLC0415

        entries = who_listing()
        if not entries:
            self.msg("No one is online.")
            return
        lines = ["|wOnline:|n"]
        for entry in entries:
            suffix = f"  |x({entry.idle})|n" if entry.idle else ""
            lines.append(f"  |w{entry.name}|n{suffix}")
        self.msg("\n".join(lines))
