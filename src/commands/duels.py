"""Duel-lifecycle telnet command — the ``duel <subverb>`` namespace (#1492).

A single command routes the PC-vs-PC duel-lifecycle verbs (challenge, accept,
decline, withdraw, risk) through the shared ``dispatch_player_action`` seam — the
same REGISTRY path the web uses, reaching the existing duel Actions in
``actions/definitions/duels.py``. No new game logic lives here; the command only
parses telnet text and dispatches.

The verbs live under the ``duel`` namespace rather than as bare top-level keys
because ``accept`` / ``decline`` collide with ``CmdAccept`` / ``CmdDeny`` (consent
and offer responses). Mirrors ``CmdRitual`` (subverb routing) and ``CmdCombat``
(the namespaced status-hub pattern). ``yield`` (concede an active duel) stays on
``combat yield`` (#1453); the status hub points to it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef

# subverb -> registry action key. ``risk`` is the short verb for acknowledge-risk.
_SUBVERBS: dict[str, str] = {
    "challenge": "challenge",
    "accept": "accept",
    "decline": "decline",
    "withdraw": "withdraw",
    "risk": "acknowledge_risk",
}

# subverbs that take a single target-name argument.
_TARGET_SUBVERBS = frozenset({"challenge"})
# subverbs that take an optional numeric challenge id.
_ID_SUBVERBS = frozenset({"accept", "decline", "withdraw"})


class CmdDuel(DispatchCommand):
    """Issue or answer a PC-vs-PC duel challenge.

    Usage:
        duel                        — show your pending challenges + duel state
        duel challenge <name>       — challenge a co-located character to a duel
        duel accept [id]            — accept a pending challenge directed at you
        duel decline [id]           — decline a pending challenge directed at you
        duel withdraw [id]          — rescind a pending challenge you issued
        duel risk                   — acknowledge the lethal risk of your duel

    The optional ``id`` selects a specific pending challenge when you have more
    than one; without it the command acts on your single pending challenge. To
    concede an active duel, use ``combat yield``.
    """

    key = "duel"
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        """Route the leading subverb; bare ``duel`` shows the status hub."""
        raw = (self.args or "").strip()
        if not raw:
            self._show_status_hub()
            return
        parts = raw.split(maxsplit=1)
        self._subverb = parts[0].lower()
        self._rest = parts[1].strip() if len(parts) > 1 else ""
        if self._subverb not in _SUBVERBS:
            options = ", ".join(_SUBVERBS)
            self.msg(f"Unknown duel action '{self._subverb}'. Try: {options}.")
            return
        super().func()  # resolve_action_ref + resolve_action_args + dispatch

    def resolve_action_ref(self) -> ActionRef:
        """Build a REGISTRY ActionRef for the parsed subverb."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key=_SUBVERBS[self._subverb])

    def resolve_action_args(self) -> dict[str, Any]:
        """Resolve the subverb's arguments into dispatch kwargs."""
        if self._subverb in _TARGET_SUBVERBS:
            target = self.search_or_raise(self._require_rest("a target name"))
            return {"target": target}
        if self._subverb in _ID_SUBVERBS:
            challenge_id = self._parse_optional_id()
            return {} if challenge_id is None else {"challenge_id": challenge_id}
        return {}  # risk — no arguments

    # -- helpers ---------------------------------------------------------------

    def _require_rest(self, what: str) -> str:
        if not self._rest:
            msg = f"Usage: duel {self._subverb} <{what}>."
            raise CommandError(msg)
        return self._rest

    def _parse_optional_id(self) -> int | None:
        """Return the optional numeric challenge id, or None when omitted."""
        if not self._rest:
            return None
        if not self._rest.isdigit():
            msg = f"Usage: duel {self._subverb} [<challenge id>]."
            raise CommandError(msg)
        return int(self._rest)

    def _incoming_challenge(self) -> Any:
        """Return the caller's single PENDING incoming challenge, or None."""
        from actions.definitions.duels import _pending_challenge_for_challenged  # noqa: PLC0415

        return _pending_challenge_for_challenged(self.caller)

    def _outgoing_challenge(self) -> Any:
        """Return the caller's single PENDING outgoing challenge, or None."""
        from actions.definitions.duels import _pending_challenge_for_challenger  # noqa: PLC0415

        return _pending_challenge_for_challenger(self.caller)

    def _active_duel(self) -> Any:
        """Return the caller's active DUEL CombatParticipant, or None."""
        from actions.definitions.duels import _active_duel_participant  # noqa: PLC0415

        return _active_duel_participant(self.caller)

    def _show_status_hub(self) -> None:
        """Print the caller's pending challenges and current duel state."""
        lines = [
            "|wDuel actions|n: challenge <name>, accept [id], decline [id], withdraw [id], risk"
        ]
        incoming = self._incoming_challenge()
        outgoing = self._outgoing_challenge()
        participant = self._active_duel()
        if incoming is not None:
            challenger = incoming.challenger_sheet.character.db_key
            lines.append(
                f"Pending challenge from {challenger} (#{incoming.pk}) — "
                "duel accept / duel decline."
            )
        if outgoing is not None:
            challenged = outgoing.challenged_sheet.character.db_key
            lines.append(f"You have challenged {challenged} (#{outgoing.pk}) — duel withdraw.")
        if participant is not None:
            if participant.encounter.is_lethal:
                lines.append(
                    "You are in a lethal duel — duel risk to acknowledge the risk, "
                    "combat yield to concede."
                )
            else:
                lines.append("You are in a duel — combat yield to concede.")
        if incoming is None and outgoing is None and participant is None:
            lines.append("You have no pending duel challenges.")
        self.msg("\n".join(lines))
