"""Signature telnet command — the ``signature <subverb>`` namespace (#1582).

A single command routes the three signature-bonus lifecycle verbs through the
shared ``dispatch_player_action`` seam.  No game logic lives here; the command
only parses telnet text and resolves objects before dispatching to the REGISTRY
actions in ``actions/definitions/signature.py``.

The verbs live under the ``signature`` namespace to avoid broad one-word key
collisions with exits/channels/aliases (same reasoning as ``CmdSanctum`` /
``CmdCombat``).  Technique lookup uses exact-name matching because Evennia's
partial/fuzzy search is broken on PostgreSQL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef

# Subverb name constants (used in comparisons — avoids STRING_LITERAL lint).
_SUBVERB_LIST = "list"
_SUBVERB_SET = "set"
_SUBVERB_CLEAR = "clear"

# subverb → registry action key.
_SUBVERBS: dict[str, str] = {
    _SUBVERB_SET: "signature_set",
    _SUBVERB_CLEAR: "signature_clear",
    _SUBVERB_LIST: "signature_list",
}

# Telnet kwarg token keys.
_TECHNIQUE_KWARG = "technique"
_BONUS_KWARG = "bonus"


def _parse_kwargs(args: str) -> dict[str, str]:
    """Parse ``key=value`` tokens from *args*, left to right.

    A value runs from the ``=`` to the start of the next ``key=`` token (or end
    of string), so multi-word values like ``technique=Flame Strike`` are captured
    whole.  Tokens that precede the first ``key=`` are accumulated under the
    ``_positional`` key (space-joined).  Unknown keys are silently kept so error
    handling can surface a usage message.
    """
    out: dict[str, str] = {}
    positional: list[str] = []
    tokens = args.split()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if "=" in token:
            key, _, first_val = token.partition("=")
            value_parts: list[str] = [first_val] if first_val else []
            i += 1
            while i < len(tokens) and "=" not in tokens[i]:
                value_parts.append(tokens[i])
                i += 1
            out[key] = " ".join(value_parts)
        else:
            positional.append(token)
            i += 1
    if positional:
        out["_positional"] = " ".join(positional)
    return out


class CmdSignature(DispatchCommand):
    """Manage signature bonuses on technique threads.

    Usage:
        signature                              — list available bonuses + current settings
        signature list                         — (same)
        signature set technique=<name> bonus=<name>
                                               — attach a bonus to a technique thread
        signature clear technique=<name>       — remove the current bonus
    """

    key = "signature"
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        """Route the leading subverb; bare ``signature`` / ``signature list`` shows the hub."""
        raw = (self.args or "").strip()
        if not raw or raw.lower() == _SUBVERB_LIST:
            self._subverb = _SUBVERB_LIST
            self._rest = ""
            super().func()
            return
        parts = raw.split(maxsplit=1)
        self._subverb = parts[0].lower()
        self._rest = parts[1].strip() if len(parts) > 1 else ""
        if self._subverb not in _SUBVERBS:
            options = ", ".join(_SUBVERBS)
            self.msg(f"Unknown signature action '{self._subverb}'. Try: {options}.")
            return
        super().func()  # resolve_action_ref + resolve_action_args + dispatch

    def resolve_action_ref(self) -> ActionRef:
        """Build a REGISTRY ActionRef for the parsed subverb."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key=_SUBVERBS[self._subverb])

    def resolve_action_args(self) -> dict[str, Any]:
        """Resolve the subverb's arguments into dispatch kwargs."""
        parsed = _parse_kwargs(self._rest)
        if self._subverb == _SUBVERB_LIST:
            return {}
        if self._subverb == _SUBVERB_SET:
            return self._args_set(parsed)
        if self._subverb == _SUBVERB_CLEAR:
            return self._args_clear(parsed)
        return {}  # unreachable — func() gates on _SUBVERBS

    # -- per-subverb argument resolvers ----------------------------------------

    def _require_technique_thread(self, technique_name: str) -> Any:
        """Resolve *technique_name* to an active TECHNIQUE Thread, or raise CommandError.

        Uses exact-name matching (Evennia partial search is broken on PG).
        Looks up the character's :class:`CharacterTechnique` rows to confirm
        ownership, then finds the active thread via the cached handler.
        """
        from world.magic.constants import TargetKind  # noqa: PLC0415
        from world.magic.models import CharacterTechnique  # noqa: PLC0415

        sheet = self.caller.character_sheet
        if sheet is None:
            msg = "No active character."
            raise CommandError(msg)

        ct = (
            CharacterTechnique.objects.filter(
                character=sheet,
                technique__name__iexact=technique_name,
            )
            .select_related("technique")
            .first()
        )
        if ct is None:
            msg = f"You don't know a technique called '{technique_name}'."
            raise CommandError(msg)

        technique = ct.technique
        thread = next(
            (
                t
                for t in self.caller.threads.all()
                if (
                    t.target_kind == TargetKind.TECHNIQUE
                    and t.target_technique_id == technique.pk
                    and t.retired_at is None
                )
            ),
            None,
        )
        if thread is None:
            msg = (
                f"You have no active thread woven for '{technique.name}'. "
                "Weave one first (see 'weave')."
            )
            raise CommandError(msg)
        return thread

    def _require_bonus(self, bonus_name: str) -> Any:
        """Resolve *bonus_name* to a SignatureMotifBonus (iexact), or raise CommandError."""
        from world.magic.models.signature import SignatureMotifBonus  # noqa: PLC0415

        if not bonus_name:
            msg = "Specify a bonus: bonus=<name>."
            raise CommandError(msg)
        bonus = SignatureMotifBonus.objects.filter(name__iexact=bonus_name).first()
        if bonus is None:
            msg = f"There is no signature bonus called '{bonus_name}'."
            raise CommandError(msg)
        return bonus

    def _args_set(self, parsed: dict[str, str]) -> dict[str, Any]:
        """Resolve set kwargs: thread, bonus."""
        technique_name = parsed.get(_TECHNIQUE_KWARG, "").strip()
        if not technique_name:
            msg = "Usage: signature set technique=<name> bonus=<name>."
            raise CommandError(msg)
        bonus_name = parsed.get(_BONUS_KWARG, "").strip()
        if not bonus_name:
            msg = "Specify a bonus: bonus=<name>."
            raise CommandError(msg)
        thread = self._require_technique_thread(technique_name)
        bonus = self._require_bonus(bonus_name)
        return {"thread": thread, "bonus": bonus}

    def _args_clear(self, parsed: dict[str, str]) -> dict[str, Any]:
        """Resolve clear kwargs: thread."""
        technique_name = parsed.get(_TECHNIQUE_KWARG, "").strip()
        if not technique_name:
            msg = "Usage: signature clear technique=<name>."
            raise CommandError(msg)
        thread = self._require_technique_thread(technique_name)
        return {"thread": thread}
