"""Telnet ``where`` command (#1463) — the public presence / navigation surface.

A thin read over ``world.areas.services.where_listing``: who is out in public rooms,
each with their coloured area-hierarchy path (City - Ward - … - Room). Private rooms and
private RP stay off ``where`` (the #1287 privacy invariant). The web frontend can offer
the same data through the one service.
"""

from __future__ import annotations

from commands.command import ArxCommand


class CmdWhere(ArxCommand):
    """See who is out and about in the public spaces of the world, and where.

    Characters in public rooms are listed with their location path; private rooms and
    private scenes never appear here.

    Usage:
      where
    """

    key = "where"
    locks = "cmd:all()"
    help_category = "General"
    action = None

    def func(self) -> None:
        from world.areas.services import where_listing  # noqa: PLC0415

        entries = where_listing()
        if not entries:
            self.msg("No one is out and about in public spaces right now.")
            return
        lines = [
            "|wWho's about:|n",
            *(f"  |w{entry.persona_name}|n: {entry.room_path}" for entry in entries),
        ]
        self.msg("\n".join(lines))
