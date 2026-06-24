"""Telnet ``tidings`` command (#1450) — the pull/browse face of the public-reaction feed.

A thin wrapper over ``world.tidings.services.public_feed_for``: recent public events (deeds your
societies celebrate, scandals they whisper about) scoped to what your active character would have
heard. The web frontend offers the same feed; both converge on the one service. Pull/browse only —
the immersive *push* echoes and in-world criers/hubs are later slices of the public-reaction epic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.tidings.constants import FeedItemKind

if TYPE_CHECKING:
    from world.scenes.models import Persona
    from world.tidings.services import PublicFeedItem

_NO_IDENTITY = "You have no active character to catch up on the tidings with."
_EMPTY = "There are no tidings circulating in your circles right now."


class CmdTidings(ArxCommand):
    """Catch up on the tidings your character's circles would have heard.

    Deeds your societies celebrate and scandals they whisper about, newest first — scoped to the
    societies and organizations your active character belongs to.

    Usage:
      tidings
    """

    key = "tidings"
    locks = "cmd:all()"
    action = None

    def func(self) -> None:
        try:
            persona = self._caller_persona()
        except CommandError as exc:
            self.msg(str(exc))
            return
        from world.tidings.services import public_feed_for  # noqa: PLC0415

        feed = public_feed_for(persona)
        if not feed:
            self.msg(_EMPTY)
            return
        lines = ["|wThe tidings of your circles:|n", *(self._format(item) for item in feed)]
        self.msg("\n".join(lines))

    def _caller_persona(self) -> Persona:
        from world.roster.models import RosterEntry  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        entry = RosterEntry.objects.filter(character_sheet__character=self.caller).first()
        if entry is None:
            raise CommandError(_NO_IDENTITY)
        return active_persona_for_sheet(entry.character_sheet)

    @staticmethod
    def _format(item: PublicFeedItem) -> str:
        tag = "|gDEED|n" if item.kind == FeedItemKind.DEED else "|rSCANDAL|n"
        return f"  [{tag}] {item.subject}: {item.headline}"
