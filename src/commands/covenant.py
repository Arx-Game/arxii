"""Telnet covenant lifecycle namespace command (#1346).

One ``covenant`` command routes a leading subverb to the seven covenant
lifecycle Actions — engage/disengage/leave/kick/rank/transfer/standdown.
Bare ``covenant`` or ``covenant list`` renders the caller's memberships.
No business logic lives here: parse, resolve model instances, call Action.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.covenants.models import CharacterCovenantRole, Covenant, CovenantRank

_MIN_RANK_ARGS = 2  # covenant rank <char> <rank> requires at least two tokens


class CmdCovenant(ArxCommand):
    """Manage your covenant membership.

    Syntax:
        covenant [list]
        covenant engage [<covenant>]
        covenant disengage [<covenant>]
        covenant leave [<covenant>]
        covenant kick <char> [in <covenant>]
        covenant rank <char> <rank> [in <covenant>]
        covenant transfer <char> [in <covenant>]
        covenant standdown [<covenant>]

    Bare ``covenant`` shows your current memberships. Supply the covenant
    name when you belong to more than one.
    """

    key = "covenant"
    locks = "cmd:all()"
    action = None  # routes to multiple actions

    def func(self) -> None:
        try:
            self._dispatch()
        except CommandError as err:
            self.msg(str(err))

    # ------------------------------------------------------------------
    # Dispatch

    def _dispatch(self) -> None:
        args = (self.args or "").strip()
        if not args:
            self._list()
            return
        tokens: list[str] = list(args.split())
        first = tokens[0].lower()
        rest = tokens[1:]

        if first == "list":  # noqa: STRING_LITERAL
            self._list()
        elif first == "engage":  # noqa: STRING_LITERAL
            self._engage(rest)
        elif first == "disengage":  # noqa: STRING_LITERAL
            self._disengage(rest)
        elif first == "leave":  # noqa: STRING_LITERAL
            self._leave(rest)
        elif first == "kick":  # noqa: STRING_LITERAL
            self._kick(rest)
        elif first == "rank":  # noqa: STRING_LITERAL
            self._rank(rest)
        elif first == "transfer":  # noqa: STRING_LITERAL
            self._transfer(rest)
        elif first == "standdown":  # noqa: STRING_LITERAL
            self._standdown(rest)
        else:
            msg = "Usage: covenant [list|engage|disengage|leave|kick|rank|transfer|standdown] ..."
            raise CommandError(msg)

    # ------------------------------------------------------------------
    # Resolution helpers

    def _actor_sheet(self) -> Any:
        sheet = getattr(self.caller, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is None:
            msg = "You have no character sheet."
            raise CommandError(msg)
        return sheet

    def _resolve_covenant(self, name: str | None) -> CharacterCovenantRole:
        """Caller's active membership in the named covenant (or sole active one).

        If *name* is None and the caller has exactly one active membership,
        that membership is returned. If None and the caller is in multiple
        covenants, a ``CommandError`` listing the covenant names is raised.
        """
        from world.covenants.selectors import get_active_memberships  # noqa: PLC0415

        sheet = self._actor_sheet()
        memberships = get_active_memberships(character_sheet=sheet)
        if not memberships:
            msg = "You are not a member of any covenant."
            raise CommandError(msg)
        if name is None:
            if len(memberships) == 1:
                return memberships[0]
            names = ", ".join(m.covenant.name for m in memberships)
            msg = f"Which covenant? You are in: {names}"
            raise CommandError(msg)
        for m in memberships:
            if m.covenant.name.lower() == name.lower():
                return m
        msg = f"You are not a member of a covenant named '{name}'."
        raise CommandError(msg)

    def _resolve_member(self, char_name: str, covenant: Covenant) -> CharacterCovenantRole:
        """Resolve a covenant member by character name."""
        from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415

        target = self.caller.search(char_name)
        if not target:
            msg = f"Could not find '{char_name}'."
            raise CommandError(msg)
        target_sheet = getattr(target, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if target_sheet is None:
            msg = f"'{char_name}' has no character sheet."
            raise CommandError(msg)
        membership = CharacterCovenantRole.objects.filter(
            character_sheet=target_sheet, covenant=covenant, left_at__isnull=True
        ).first()
        if membership is None:
            msg = f"'{char_name}' is not a member of that covenant."
            raise CommandError(msg)
        return membership

    def _resolve_rank(self, rank_name: str, covenant: Covenant) -> CovenantRank:
        """Resolve a covenant rank by name (case-insensitive)."""
        from world.covenants.models import CovenantRank  # noqa: PLC0415

        rank = CovenantRank.objects.filter(covenant=covenant, name__iexact=rank_name).first()
        if rank is None:
            msg = f"No rank called '{rank_name}' in that covenant."
            raise CommandError(msg)
        return rank

    @staticmethod
    def _parse_in_covenant(tokens: list[str]) -> tuple[list[str], str | None]:
        """Pop a trailing ``… in <covenant>`` phrase from *tokens*.

        Returns ``(remaining_tokens, covenant_name | None)``.
        """
        lower = [t.lower() for t in tokens]
        try:
            in_idx = lower.index("in")
        except ValueError:
            return tokens, None
        covenant_name = " ".join(tokens[in_idx + 1 :]).strip() or None
        return tokens[:in_idx], covenant_name

    def _send(self, result: Any) -> None:
        self.msg(result.message)

    # ------------------------------------------------------------------
    # Subverb handlers

    def _list(self) -> None:
        from world.covenants.selectors import get_active_memberships  # noqa: PLC0415

        sheet = self._actor_sheet()
        memberships = get_active_memberships(character_sheet=sheet)
        if not memberships:
            self.msg("You are not a member of any covenant.")
            return
        lines = ["Your covenant memberships:"]
        for m in memberships:
            status = "engaged" if m.engaged else "disengaged"
            rank_name = m.rank.name if m.rank else "No rank"
            lines.append(
                f"  {m.covenant.name}  ({m.covenant_role.name})  [Rank: {rank_name}]  [{status}]"
            )
        self.msg("\n".join(lines))

    def _engage(self, rest: list[str]) -> None:
        from actions.definitions.covenants import EngageCovenantMembershipAction  # noqa: PLC0415

        name = " ".join(rest).strip() or None
        membership = self._resolve_covenant(name)
        result = EngageCovenantMembershipAction().run(actor=self.caller, membership=membership)
        self._send(result)

    def _disengage(self, rest: list[str]) -> None:
        from actions.definitions.covenants import (  # noqa: PLC0415
            DisengageCovenantMembershipAction,
        )

        name = " ".join(rest).strip() or None
        membership = self._resolve_covenant(name)
        result = DisengageCovenantMembershipAction().run(actor=self.caller, membership=membership)
        self._send(result)

    def _leave(self, rest: list[str]) -> None:
        from actions.definitions.covenants import LeaveCovenantAction  # noqa: PLC0415

        name = " ".join(rest).strip() or None
        membership = self._resolve_covenant(name)
        result = LeaveCovenantAction().run(actor=self.caller, membership=membership)
        self._send(result)

    def _kick(self, rest: list[str]) -> None:
        from actions.definitions.covenants import KickCovenantMemberAction  # noqa: PLC0415
        from world.covenants.selectors import resolve_actor_membership  # noqa: PLC0415

        rest, covenant_name = self._parse_in_covenant(rest)
        char_name = " ".join(rest).strip()
        if not char_name:
            msg = "Kick whom? (covenant kick <char> [in <covenant>])"
            raise CommandError(msg)
        actor_self = self._resolve_covenant(covenant_name)
        actor_membership = resolve_actor_membership(
            covenant=actor_self.covenant,
            character_sheets=[self._actor_sheet()],
            capability="can_kick",
        )
        if actor_membership is None:
            msg = "You lack the authority to remove members from that covenant."
            raise CommandError(msg)
        target = self._resolve_member(char_name, actor_self.covenant)
        result = KickCovenantMemberAction().run(
            actor=self.caller, target=target, actor_membership=actor_membership
        )
        self._send(result)

    def _rank(self, rest: list[str]) -> None:
        from actions.definitions.covenants import AssignCovenantRankAction  # noqa: PLC0415
        from world.covenants.selectors import resolve_actor_membership  # noqa: PLC0415

        rest, covenant_name = self._parse_in_covenant(rest)
        if len(rest) < _MIN_RANK_ARGS:
            msg = "Usage: covenant rank <char> <rank> [in <covenant>]"
            raise CommandError(msg)
        rank_name = rest[-1]
        char_name = " ".join(rest[:-1]).strip()
        actor_self = self._resolve_covenant(covenant_name)
        actor_membership = resolve_actor_membership(
            covenant=actor_self.covenant,
            character_sheets=[self._actor_sheet()],
            capability="can_manage_ranks",
        )
        if actor_membership is None:
            msg = "You lack the authority to assign ranks in that covenant."
            raise CommandError(msg)
        target = self._resolve_member(char_name, actor_self.covenant)
        rank = self._resolve_rank(rank_name, actor_self.covenant)
        result = AssignCovenantRankAction().run(
            actor=self.caller,
            membership=target,
            actor_membership=actor_membership,
            rank=rank,
        )
        self._send(result)

    def _transfer(self, rest: list[str]) -> None:
        from actions.definitions.covenants import TransferTopRankAction  # noqa: PLC0415
        from world.covenants.selectors import resolve_actor_membership  # noqa: PLC0415

        rest, covenant_name = self._parse_in_covenant(rest)
        char_name = " ".join(rest).strip()
        if not char_name:
            msg = "Transfer to whom? (covenant transfer <char> [in <covenant>])"
            raise CommandError(msg)
        actor_self = self._resolve_covenant(covenant_name)
        actor_membership = resolve_actor_membership(
            covenant=actor_self.covenant,
            character_sheets=[self._actor_sheet()],
            capability="can_manage_ranks",
        )
        if actor_membership is None:
            msg = "You lack the authority to transfer ranks in that covenant."
            raise CommandError(msg)
        new_top = self._resolve_member(char_name, actor_self.covenant)
        result = TransferTopRankAction().run(
            actor=self.caller,
            covenant=actor_self.covenant,
            actor_membership=actor_membership,
            new_top_membership=new_top,
        )
        self._send(result)

    def _standdown(self, rest: list[str]) -> None:
        from actions.definitions.covenants import StandDownBattleCovenantAction  # noqa: PLC0415

        name = " ".join(rest).strip() or None
        membership = self._resolve_covenant(name)
        result = StandDownBattleCovenantAction().run(
            actor=self.caller, covenant=membership.covenant
        )
        self._send(result)
