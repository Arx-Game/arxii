"""Organization membership lifecycle telnet command — the `org <subverb>` namespace (#1511).

Mirrors `CmdDuel` and `CmdCombat`: a single namespace routes the lifecycle
verbs through the shared `dispatch_player_action` seam so the telnet path and
web path converge on the same actions.
"""

from __future__ import annotations

from typing import Any

from actions.constants import ActionBackend
from actions.types import ActionRef
from commands.command import DispatchCommand
from commands.exceptions import CommandError
from world.societies.models import Organization

_SUBVERBS: dict[str, str] = {
    "invite": "org_invite",
    "apply": "org_apply",
    "join": "org_join",
    "leave": "org_leave",
    "promote": "org_promote",
    "demote": "org_demote",
    "expel": "org_expel",
}

_TWO_ARG_SUBVERBS = frozenset({"invite", "promote", "demote", "expel"})
_ONE_ARG_SUBVERBS = frozenset({"apply", "join", "leave"})


class CmdOrg(DispatchCommand):
    """Manage organization membership.

    Usage:
        org                              — list subverbs
        org invite <person> in <org>   — invite a co-located character
        org apply <org>                  — apply to join an organization
        org join <org>                   — accept a pending invitation
        org leave <org>                  — leave an organization
        org promote <person> in <org>    — promote a lower-ranked member
        org demote <person> in <org>    — demote a lower-ranked member
        org expel <person> in <org>     — forcibly remove a lower-ranked member
    """

    key = "org"
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        raw = (self.args or "").strip()
        if not raw:
            self._show_hub()
            return

        parts = raw.split(maxsplit=1)
        self._subverb = parts[0].lower()
        self._rest = parts[1].strip() if len(parts) > 1 else ""

        if self._subverb not in _SUBVERBS:
            self.msg(f"Unknown org action '{self._subverb}'. Try: {', '.join(_SUBVERBS)}.")
            return

        super().func()

    def resolve_action_ref(self) -> ActionRef:
        return ActionRef(
            backend=ActionBackend.REGISTRY,
            registry_key=_SUBVERBS[self._subverb],
        )

    def resolve_action_args(self) -> dict[str, Any]:
        if self._subverb in _TWO_ARG_SUBVERBS:
            target_name, org_name = self.parse_two_args(
                "in",
                empty_msg=f"Usage: org {self._subverb} <person> in <organization>.",
                usage_msg=f"Usage: org {self._subverb} <person> in <organization>.",
            )
            target = self.search_or_raise(target_name)
            return {
                "target": target,
                "organization_id": self._resolve_org(org_name).pk,
            }

        if self._subverb in _ONE_ARG_SUBVERBS:
            org_name = self._require_rest(f"Usage: org {self._subverb} <organization>.")
            return {"organization_id": self._resolve_org(org_name).pk}

        return {}

    def _resolve_org(self, value: str) -> Organization:
        return self.resolve_by_name_or_id(
            Organization,
            value,
            not_found_msg=f"Could not find organization '{value}'.",
        )

    def _require_rest(self, usage: str) -> str:
        if not self._rest:
            raise CommandError(usage)
        return self._rest

    def _show_hub(self) -> None:
        self.msg(
            "Org actions: invite <person> in <org>, apply <org>, join <org>, "
            "leave <org>, promote <person> in <org>, demote <person> in <org>, "
            "expel <person> in <org>."
        )
