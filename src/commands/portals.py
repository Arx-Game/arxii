"""Telnet `portal` command (#2222) — dispatches Install/DissolvePortalAnchorAction.

Switch-routed, mirrors ``CmdRoom``'s manual switch dispatch (`locations.py`).
Resolves the anchor kind (and, for dissolve, disambiguates a room's anchor
set by kind) from telnet text before calling the actions' ``.run()``
directly — thin shell, all business logic lives in
``actions/definitions/portals.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.definitions.portals import (
    DissolvePortalAnchorAction,
    InstallPortalAnchorAction,
    anchors_in_room,
)
from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.magic.models import PortalAnchorKind

_SWITCH_INSTALL = "install"
_SWITCH_DISSOLVE = "dissolve"
_USAGE = "Usage: portal/install <kind>=<name> | portal/dissolve [<kind>]"


class CmdPortalAnchor(ArxCommand):
    """Install or dissolve a portal anchor in your current room.

    Usage:
      portal/install <kind>=<name>
      portal/dissolve [<kind>]
    """

    key = "portal"
    locks = "cmd:all()"

    def func(self) -> None:
        try:
            self._dispatch()
        except CommandError as err:
            self.msg(str(err))

    def _dispatch(self) -> None:
        switches = {s.lower() for s in (self.switches or [])}
        args = (self.args or "").strip()
        if _SWITCH_INSTALL in switches:
            self._do_install(args)
            return
        if _SWITCH_DISSOLVE in switches:
            self._do_dissolve(args)
            return
        raise CommandError(_USAGE)

    @staticmethod
    def _resolve_kind(name: str) -> PortalAnchorKind:
        from world.magic.models import PortalAnchorKind  # noqa: PLC0415

        kind = PortalAnchorKind.objects.filter(name__iexact=name).first()
        if kind is None:
            msg = f"There is no portal anchor kind called '{name}'."
            raise CommandError(msg)
        return kind

    def _do_install(self, args: str) -> None:
        kind_part, sep, name_part = args.partition("=")
        kind_name = kind_part.strip()
        anchor_name = name_part.strip()
        if not sep or not kind_name or not anchor_name:
            msg = "Usage: portal/install <kind>=<name>"
            raise CommandError(msg)
        kind = self._resolve_kind(kind_name)
        result = InstallPortalAnchorAction().run(self.caller, kind=kind, name=anchor_name)
        if result.message:
            self.msg(result.message)

    def _do_dissolve(self, args: str) -> None:
        kwargs = {}
        if args:
            kind = self._resolve_kind(args)
            candidates = anchors_in_room(self.caller.location)
            anchor = next((a for a in candidates if a.kind_id == kind.pk), None)
            if anchor is None:
                msg = f"There is no active {kind.name} anchor here."
                raise CommandError(msg)
            kwargs["anchor"] = anchor
        result = DissolvePortalAnchorAction().run(self.caller, **kwargs)
        if result.message:
            self.msg(result.message)
