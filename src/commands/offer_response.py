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
        from commands.offer_registry import find_handler, get_all_pending  # noqa: PLC0415

        sheet = getattr(self.caller, "sheet_data", None)  # noqa: GETATTR_LITERAL
        args = (self.args or "").strip()

        if not args:
            pending = get_all_pending(sheet) if sheet is not None else []
            if pending:
                lines = ["Pending prompts:"]
                lines += [f"  [{h.keyword}] {h.describe(o)}" for h, o in pending]
                self.msg("\n".join(lines))
            else:
                self.msg("You have no pending offers.")
            return

        keyword, _, _ = args.partition(" ")
        handler = find_handler(keyword)
        if handler is None:
            self.msg(f"No pending prompt type '{keyword}'.")
            return
        if sheet is None:
            self.msg("You need a character sheet for that.")
            return
        offer = handler.pending_for(sheet)
        if offer is None:
            self.msg(f"You have no pending {handler.label} offer.")
            return
        try:
            self.msg(handler.decline(offer, self.caller))
        except CommandError as exc:
            self.msg(str(exc))
