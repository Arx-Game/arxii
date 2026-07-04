"""Telnet ``tidings`` command (#1450) — the pull/browse face of the public-reaction feed.

A thin wrapper over ``world.tidings.services``: recent public events (deeds your societies
celebrate, scandals they whisper about) scoped to what your active character would have heard.
The web frontend offers the same feed; both converge on the one service.

Two scopes:

- ``tidings`` — your circles (the persona's societies + orgs).
- ``tidings local`` — the civic-hub slice: what the notice board carries or the crier calls in
  THIS room. Only works where a hub feature stands (Notice Board / Town Crier, #1450).
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
_NO_HUB = "There is no notice board or crier here; local tidings are found where folk gather."
_LOCAL_EMPTY = "The local tidings are quiet; nothing worth repeating today."
_USAGE = "Usage: tidings  or  tidings local"
_LOCAL_SUBVERB = "local"

# PLACEHOLDER flavor headers (Apostate rewrite pass; keep dash-free).
_BOARD_HEADER = "|wPinned to the notice board:|n"
_CRIER_HEADER = "|wThe crier calls out the news of the day:|n"


class CmdTidings(ArxCommand):
    """Catch up on the tidings your character's circles would have heard.

    Deeds your societies celebrate and scandals they whisper about, newest first — scoped to the
    societies and organizations your active character belongs to. In a room with a notice board
    or town crier, ``tidings local`` reads the local slice instead.

    Usage:
      tidings
      tidings local
    """

    key = "tidings"
    locks = "cmd:all()"
    action = None

    def func(self) -> None:
        arg = self.args.strip().lower()
        if arg == _LOCAL_SUBVERB:
            self._local_tidings()
            return
        if arg:
            self.msg(_USAGE)
            return
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

    def _local_tidings(self) -> None:
        """The civic-hub scope: gated on the room carrying a hub feature."""
        from world.areas.services import get_room_profile  # noqa: PLC0415
        from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
        from world.room_features.services import active_hub_feature  # noqa: PLC0415
        from world.tidings.services import hub_feed_for_room  # noqa: PLC0415

        room = self.caller.location
        feature = active_hub_feature(get_room_profile(room)) if room is not None else None
        if feature is None:
            self.msg(_NO_HUB)
            return
        feed = hub_feed_for_room(room)
        if not feed:
            self.msg(_LOCAL_EMPTY)
            return
        is_crier = feature.feature_kind.service_strategy == RoomFeatureServiceStrategy.TOWN_CRIER
        header = _CRIER_HEADER if is_crier else _BOARD_HEADER
        self.msg("\n".join([header, *(self._format(item) for item in feed)]))

    def _caller_persona(self) -> Persona:
        from world.roster.models import RosterEntry  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        entry = RosterEntry.objects.filter(character_sheet__character=self.caller).first()
        if entry is None:
            raise CommandError(_NO_IDENTITY)
        return active_persona_for_sheet(entry.character_sheet)

    @staticmethod
    def _format(item: PublicFeedItem) -> str:
        if item.category:
            tag = f"|r{item.category}|n"
        elif item.kind == FeedItemKind.DEED:
            tag = "|gDEED|n"
        else:
            tag = "|rSCANDAL|n"
        return f"  [{tag}] {item.subject}: {item.headline}"
