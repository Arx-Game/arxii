from __future__ import annotations

from commands.command import ArxCommand
from commands.exceptions import CommandError


class CmdDecline(ArxCommand):
    """Decline a pending game prompt.

    Usage:
        decline              — list pending offers
        decline <keyword>    — decline the offer of that type
    """

    key = "decline"
    locks = "cmd:all()"
    action = None

    def func(self) -> None:
        try:
            self.msg(self._dispatch_decline())
        except CommandError as exc:
            self.msg(str(exc))

    def _dispatch_decline(self) -> str:
        from commands.offer_registry import (  # noqa: PLC0415
            find_handler,
            format_pending_listing,
            get_all_pending,
        )

        sheet = getattr(self.caller, "sheet_data", None)  # noqa: GETATTR_LITERAL
        args = (self.args or "").strip()
        if not args:
            return format_pending_listing(get_all_pending(sheet) if sheet is not None else [])
        keyword = args.partition(" ")[0]
        handler = find_handler(keyword)
        if handler is None:
            msg = f"No registered offer type '{keyword}'."
            raise CommandError(msg)
        if sheet is None:
            msg = "You need a character sheet for that."
            raise CommandError(msg)
        offer = handler.pending_for(sheet)
        if offer is None:
            msg = f"You have no pending {handler.label} offer."
            raise CommandError(msg)
        return handler.decline(offer, self.caller)
