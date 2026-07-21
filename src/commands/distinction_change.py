"""Distinction-change telnet command — ``dchange`` (#2607 follow-up).

Telnet surface for the post-CG distinction-change flow merged in #2624 (which
shipped web-only). Routes the GM authorize and player accept verbs through the
shared ``dispatch_player_action`` seam — the same REGISTRY path the web uses —
reaching ``AuthorizeDistinctionChangeAction`` / ``AcceptDistinctionChangeAction``
in ``actions/definitions/distinctions.py``. Bare ``dchange`` shows the caller's
pending authorizations. No business logic lives here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef

_SUBVERBS: dict[str, str] = {
    "authorize": "authorize_distinction_change",
    "accept": "accept_distinction_change",
}


def _kv(rest: str) -> dict[str, str]:
    """Parse ``key=value key=value`` telnet args into a dict."""
    out: dict[str, str] = {}
    for token in rest.split():
        if "=" in token:
            key, value = token.split("=", 1)
            out[key.strip()] = value.strip()
    return out


class CmdDistinctionChange(DispatchCommand):
    """Authorize (GM) or accept (player) a post-CG distinction change.

    Usage:
        dchange                                           — your pending authorizations
        dchange authorize target_name=<char> action=<add|remove> \
distinction_slug=<slug> reason=<...>     — GM (add)
        dchange authorize target_name=<char> action=remove \
character_distinction_id=<id> reason=<...>   — GM (remove)
        dchange accept authorization_id=<n>               — spend XP to apply an authorized change
    """

    key = "distinctionchange"
    aliases = ["dchange"]
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        raw = (self.args or "").strip()
        if not raw or raw.lower() == "status":
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
            msg = f"Usage: dchange {self._subverb} key=value ..."
            raise CommandError(msg)
        return kwargs

    def _show_hub(self) -> None:
        sheet = self.caller.character_sheet
        lines = ["|wDistinction change|n: authorize (GM) / accept <authorization_id>"]
        if sheet is None:
            self.msg("\n".join(lines))
            return
        pending = sheet.distinction_change_authorizations.filter(is_consumed=False).select_related(
            "target_distinction", "target_character_distinction__distinction"
        )[:20]
        lines.append("")
        lines.append("Your pending authorizations:")
        if not pending:
            lines.append("  (none)")
        for auth in pending:
            if auth.action == "add":
                name = auth.target_distinction.name if auth.target_distinction else "?"
            else:
                cd = auth.target_character_distinction
                name = cd.distinction.name if cd else "?"
            lines.append(f"  #{auth.pk} {auth.action} {name} — {auth.xp_cost} XP")
        self.msg("\n".join(lines))
