"""CmdSheetRequest — player + GM sheet-update request namespace (#2628).

Thin telnet face of ``SubmitSheetUpdateRequestAction`` /
``ReviewSheetUpdateRequestAction``. Namespaced subverbs (mirrors CmdCovenant).
"""

from __future__ import annotations

from typing import Any

from actions.definitions.distinctions import (
    ReviewSheetUpdateRequestAction,
    SubmitSheetUpdateRequestAction,
)
from commands.command import ArxCommand
from world.distinctions.exceptions import SheetUpdateRequestError

_USAGE = "Usage: sheetrequest <add|remove|cancel|approve|deny|list> ..."

_ADD = "add"
_REMOVE = "remove"
_CANCEL = "cancel"
_APPROVE = "approve"
_DENY = "deny"
_LIST = "list"


class CmdSheetRequest(ArxCommand):
    """Submit or review sheet-update requests.

    Players: submit add/remove requests with justification, cancel pending ones.
    GMs: approve or deny pending requests from players at their table.

    Usage:
      sheetrequest                          - list your requests
      sheetrequest add <slug>[,rank] justification=<text>
      sheetrequest remove <slug> justification=<text>
      sheetrequest cancel <id>
      sheetrequest approve <id>
      sheetrequest deny <id>
    """

    key = "sheetrequest"
    aliases = ["sheetreq"]
    locks = "cmd:all()"
    help_category = "Character"

    def func(self) -> None:
        raw = (self.args or "").strip()
        if not raw:
            self._list_requests()
            return

        parts = raw.split(None, 1)
        subverb = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""

        if subverb in (_ADD, _REMOVE):
            self._submit(subverb, rest)
        elif subverb == _CANCEL:
            self._cancel(rest)
        elif subverb == _APPROVE:
            self._review(rest, _APPROVE)
        elif subverb == _DENY:
            self._review(rest, _DENY)
        elif subverb == _LIST:
            self._list_requests()
        else:
            self.msg(_USAGE)

    def _submit(self, kind: str, rest: str) -> None:
        if "=" not in rest:
            self.msg(f"Usage: sheetrequest {kind} <slug> justification=<text>")
            return

        pre, justification = (p.strip() for p in rest.split("=", 1))
        if not pre or not justification:
            self.msg(f"Usage: sheetrequest {kind} <slug> justification=<text>")
            return

        slug = pre
        rank = None
        if "," in pre:
            slug, rank_raw = (p.strip() for p in pre.rsplit(",", 1))
            try:
                rank = int(rank_raw)
            except ValueError:
                self.msg("rank must be a whole number.")
                return

        kwargs: dict[str, Any] = {
            "request_type": f"distinction_{kind}",
            "justification": justification,
            "distinction_slug": slug,
        }
        if rank is not None:
            kwargs["rank"] = rank

        result = SubmitSheetUpdateRequestAction().run(self.caller, **kwargs)
        self.msg(result.message)

    def _cancel(self, rest: str) -> None:
        from world.distinctions.models import SheetUpdateRequest  # noqa: PLC0415
        from world.distinctions.services import cancel_sheet_update_request  # noqa: PLC0415

        try:
            req_id = int(rest.strip())
        except ValueError:
            self.msg("Usage: sheetrequest cancel <id>")
            return

        sheet = self.caller.character_sheet
        if sheet is None:
            self.msg("You have no character sheet.")
            return

        req = SheetUpdateRequest.objects.filter(pk=req_id, character_sheet=sheet).first()
        if req is None:
            self.msg(f"Request #{req_id} not found.")
            return

        account = self.caller.account
        try:
            cancel_sheet_update_request(req, account)
        except SheetUpdateRequestError as exc:
            self.msg(exc.user_message)
            return
        self.msg(f"Cancelled request #{req_id}.")

    def _review(self, rest: str, decision: str) -> None:
        try:
            req_id = int(rest.strip())
        except ValueError:
            self.msg(f"Usage: sheetrequest {decision} <id>")
            return

        result = ReviewSheetUpdateRequestAction().run(
            self.caller, request_id=req_id, decision=decision
        )
        self.msg(result.message)

    def _list_requests(self) -> None:
        from world.distinctions.models import SheetUpdateRequest  # noqa: PLC0415

        sheet = self.caller.character_sheet
        if sheet is None:
            self.msg("You have no character sheet.")
            return

        requests = SheetUpdateRequest.objects.filter(character_sheet=sheet).order_by("-created_at")[
            :20
        ]

        if not requests:
            self.msg("You have no sheet update requests.")
            return

        lines = ["Your sheet update requests:"]
        for req in requests:
            status = req.get_status_display()
            desc = req.get_request_type_display()
            if req.target_distinction:
                desc += f" ({req.target_distinction.name})"
            elif req.target_character_distinction:
                desc += f" ({req.target_character_distinction.distinction.name})"
            lines.append(f"  #{req.pk} [{status}] {desc} - {req.xp_cost} XP")
        self.msg("\n".join(lines))
