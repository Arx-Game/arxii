"""Organization membership lifecycle telnet command — the `org <subverb>` namespace (#1511).

Mirrors `CmdDuel` and `CmdCombat`: a single namespace routes the lifecycle
verbs through the shared `dispatch_player_action` seam so the telnet path and
web path converge on the same actions.

Also home to `CmdAppeal` (#3293) — appeals to organizations. A sibling
namespace, not a subverb of `org`, since its default (unlabelled) grammar
lodges an appeal rather than listing subverbs (mirrors `CmdPact`'s shape).
"""

from __future__ import annotations

from typing import Any

from actions.constants import ActionBackend
from actions.types import ActionRef
from commands.command import DispatchCommand
from commands.exceptions import CommandError
from world.societies.models import Organization, OrgAppeal

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
        org                              - list subverbs
        org invite <person> in <org>   - invite a co-located character
        org apply <org>                  - apply to join an organization
        org join <org>                   - accept a pending invitation
        org leave <org>                  - leave an organization
        org promote <person> in <org>    - promote a lower-ranked member
        org demote <person> in <org>    - demote a lower-ranked member
        org expel <person> in <org>     - forcibly remove a lower-ranked member
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


_SUBVERB_LODGE = "lodge"
_SUBVERB_LIST = "list"
_SUBVERB_SIGNON = "signon"
_SUBVERB_RESOLVE = "resolve"
_SUBVERB_WITHDRAW = "withdraw"

_APPEAL_SUBVERBS: dict[str, str] = {
    _SUBVERB_LODGE: "org_appeal_lodge",
    _SUBVERB_SIGNON: "org_appeal_signon",
    _SUBVERB_RESOLVE: "org_appeal_resolve",
    _SUBVERB_WITHDRAW: "org_appeal_withdraw",
}


class CmdAppeal(DispatchCommand):
    """Appeal to an organization for aid, and manage those appeals (#3293).

    Usage:
        appeal <org>=<title>/<body>                  - lodge an appeal
        appeal list <org>                             - list an org's appeals
        appeal signon <id>[=<note>]                    - sign onto an open appeal
        appeal resolve <id>=grant|decline/<answer>     - leadership resolves it
        appeal withdraw <id>                           - withdraw your own appeal

    Any character may lodge an appeal, even without membership. Only an
    organization's members (any rank) and the petitioner may list or read one;
    only a member with resolution standing (or staff) may resolve one.
    """

    key = "appeal"
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        raw = (self.args or "").strip()
        if not raw:
            self._show_hub()
            return

        parts = raw.split(maxsplit=1)
        head = parts[0].lower()
        if head in (_SUBVERB_LIST, *_APPEAL_SUBVERBS):
            self._subverb = head
            self._rest = parts[1].strip() if len(parts) > 1 else ""
        else:
            self._subverb = _SUBVERB_LODGE
            self._rest = raw

        if self._subverb == _SUBVERB_LIST:
            self._show_list()
            return

        super().func()

    def resolve_action_ref(self) -> ActionRef:
        return ActionRef(
            backend=ActionBackend.REGISTRY,
            registry_key=_APPEAL_SUBVERBS[self._subverb],
        )

    def resolve_action_args(self) -> dict[str, Any]:
        if self._subverb == _SUBVERB_LODGE:
            org_part, rest = self._split_once(
                self._rest, "=", "Usage: appeal <org>=<title>/<body>."
            )
            title, body = self._split_once(rest, "/", "Usage: appeal <org>=<title>/<body>.")
            return {
                "organization_id": self._resolve_org(org_part).pk,
                "title": title,
                "body": body,
            }

        if self._subverb == _SUBVERB_SIGNON:
            if "=" in self._rest:
                id_part, note = self._rest.split("=", 1)
            else:
                id_part, note = self._rest, ""
            return {"appeal_id": self._resolve_appeal_id(id_part), "note": note.strip()}

        if self._subverb == _SUBVERB_RESOLVE:
            id_part, rest = self._split_once(
                self._rest, "=", "Usage: appeal resolve <id>=grant|decline/<answer>."
            )
            verdict, answer = self._split_once(
                rest, "/", "Usage: appeal resolve <id>=grant|decline/<answer>."
            )
            return {
                "appeal_id": self._resolve_appeal_id(id_part),
                "verdict": verdict.strip(),
                "answer": answer,
            }

        if self._subverb == _SUBVERB_WITHDRAW:
            return {"appeal_id": self._resolve_appeal_id(self._rest)}

        return {}

    def _split_once(self, value: str, connector: str, usage_msg: str) -> tuple[str, str]:
        if connector not in value:
            raise CommandError(usage_msg)
        left, right = value.split(connector, 1)
        left, right = left.strip(), right.strip()
        if not left or not right:
            raise CommandError(usage_msg)
        return left, right

    def _resolve_org(self, value: str) -> Organization:
        return self.resolve_by_name_or_id(
            Organization,
            value,
            not_found_msg=f"Could not find organization '{value}'.",
        )

    def _resolve_appeal_id(self, value: str) -> int:
        value = value.strip()
        if not value.isdigit():
            msg = "Which appeal? Use its numeric id."
            raise CommandError(msg)
        return int(value)

    def _show_list(self) -> None:
        from world.societies.membership_services import (  # noqa: PLC0415
            active_membership_for_persona,
        )

        if not self._rest:
            msg = "Usage: appeal list <org>."
            raise CommandError(msg)
        organization = self._resolve_org(self._rest)

        actor_persona = self._actor_persona()
        is_staff = bool(self.caller.account and self.caller.account.is_staff)
        if actor_persona is None and not is_staff:
            self.msg("You have no character identity.")
            return

        qs = OrgAppeal.objects.filter(organization=organization)
        if not is_staff:
            is_member = (
                actor_persona is not None
                and active_membership_for_persona(organization, actor_persona) is not None
            )
            if not is_member:
                qs = qs.filter(petitioner_persona=actor_persona)

        appeals = list(qs.select_related("petitioner_persona").order_by("-created_at")[:20])
        if not appeals:
            self.msg(f"No visible appeals for {organization.name}.")
            return

        lines = [f"Appeals to {organization.name}:"]
        lines.extend(
            f"  #{appeal.pk} [{appeal.get_state_display()}] {appeal.title} "
            f"(by {appeal.petitioner_persona.name})"
            for appeal in appeals
        )
        self.msg("\n".join(lines))

    def _actor_persona(self) -> Any:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        try:
            sheet = self.caller.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return None
        if sheet is None:
            return None
        try:
            return active_persona_for_sheet(sheet)
        except ObjectDoesNotExist:
            return None

    def _show_hub(self) -> None:
        self.msg(
            "Appeal actions: <org>=<title>/<body> (lodge), list <org>, "
            "signon <id>[=<note>], resolve <id>=grant|decline/<answer>, withdraw <id>."
        )
