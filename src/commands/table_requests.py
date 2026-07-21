"""Table sheet-update request telnet command — ``tablerequest`` (#2607).

A single namespaced command routes the four request verbs through the shared
``dispatch_player_action`` seam — the same REGISTRY path the web uses — reaching
the Actions in ``actions/definitions/table_requests.py``. Bare ``tablerequest``/
``tablerequest status`` shows a hub: the caller's own requests, plus (if the
caller is a table GM) the pending requests awaiting their sign-off. Mirrors
``CmdLearn``'s namespaced-subverb shape. No business logic lives here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef

_STATUS_SUBVERB = "status"

_SUBVERBS: dict[str, str] = {
    "submit": "table_request_submit",
    "withdraw": "table_request_withdraw",
    "complete": "table_request_complete",
    "signoff": "table_request_signoff",
}


def _kv(rest: str) -> dict[str, str]:
    """Parse ``key=value key=value`` telnet args into a dict."""
    out: dict[str, str] = {}
    for token in rest.split():
        if "=" in token:
            key, value = token.split("=", 1)
            out[key.strip()] = value.strip()
    return out


class CmdTableRequest(DispatchCommand):
    """File and manage end-of-session sheet-update requests at your GM's table.

    Usage:
        tablerequest                                  — show your requests + pending sign-offs
        tablerequest submit table_id=<n> distinction_slug=<slug> removing=<0|1> [reasoning=<...>]
        tablerequest withdraw request_id=<n>          — pull a still-pending request
        tablerequest complete request_id=<n>          — apply an approved change (spends XP)
        tablerequest signoff request_id=<n> approve=<0|1> [notes=<...>]   — GM only
    """

    key = "tablerequest"
    aliases = ["treq"]
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        raw = (self.args or "").strip()
        if not raw or raw.lower() == _STATUS_SUBVERB:
            self._show_hub()
            return
        parts = raw.split(maxsplit=1)
        self._subverb = parts[0].lower()
        self._rest = parts[1].strip() if len(parts) > 1 else ""
        if self._subverb not in _SUBVERBS:
            self.msg(f"Unknown action '{self._subverb}'. Try: {', '.join(_SUBVERBS)}.")
            return
        super().func()

    def resolve_action_ref(self) -> ActionRef:
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key=_SUBVERBS[self._subverb])

    def resolve_action_args(self) -> dict[str, Any]:
        kwargs = _kv(self._rest)
        if not kwargs:
            msg = f"Usage: tablerequest {self._subverb} key=value ..."
            raise CommandError(msg)
        return kwargs

    def _show_hub(self) -> None:
        from world.gm.constants import TableRequestStatus  # noqa: PLC0415
        from world.gm.models import TableUpdateRequest  # noqa: PLC0415

        sheet = self.caller.character_sheet
        lines = ["|wTable requests|n: submit / withdraw / complete / signoff"]

        if sheet is not None:
            mine = TableUpdateRequest.objects.filter(
                membership__persona__character_sheet=sheet
            ).exclude(status=TableRequestStatus.COMPLETED)[:20]
            lines.append("")
            lines.append("Your open requests:")
            if not mine:
                lines.append("  (none)")
            for req in mine:
                lines.append(f"  #{req.pk} {req.kind} [{req.status}]")

        account = self.caller.account
        if account is not None:
            pending = TableUpdateRequest.objects.filter(
                membership__table__gm__account=account,
                status=TableRequestStatus.PENDING,
            )[:20]
            if pending:
                lines.append("")
                lines.append("Pending your sign-off (GM):")
                for req in pending:
                    lines.append(f"  #{req.pk} {req.kind} — {req.player_reasoning[:60]}")

        self.msg("\n".join(lines))
