"""Companion telnet command — the ``companion <subverb>`` namespace (#1918).

Routes the companion lifecycle verbs through ``dispatch_player_action`` — the
same REGISTRY seam the web uses. No new game logic lives here.

Mirrors ``CmdSanctum`` (subverb routing + status-hub pattern). The verbs live
under the ``companion`` namespace because several (bind, release) would collide
with existing bare keys.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef

# subverb → registry action key.
_SUBVERBS: dict[str, str] = {
    "bind": "bind_companion",
    "fight": "companion_fight",
    "deploy": "deploy_companion",
    "release": "release_companion",
}
# "list" and "status" are handled locally (status hub), not dispatched.

# Bare ``companion status`` / ``companion list`` are aliases for the hub.
_HUB_SUBVERBS = frozenset({"status", "list"})

# Telnet kwarg token keys used by _parse_kwargs / resolve_action_args.
_ARCHETYPE_KWARG = "archetype"
_GIFT_KWARG = "gift"
_NAME_KWARG = "name"

_MAX_NAME_LENGTH = 100

# Subverbs whose only kwarg is bind's parsed kwargs.
_BIND_SUBVERB = "bind"

# Subverbs that take a single bare companion identifier (positional, not key=value).
_POSITIONAL_SUBVERBS = frozenset({"release", "fight", "deploy"})


def _parse_kwargs(args: str) -> dict[str, str]:
    """Parse ``key=value`` tokens, left to right.

    ``name`` greedily consumes the rest of the line so companion names may
    contain spaces (and must be the final token). All other values are single
    whitespace-delimited tokens. Tokens that contain no ``=`` are silently
    skipped (positional leftovers).
    """
    out: dict[str, str] = {}
    tokens = args.split()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if "=" not in token:
            index += 1
            continue
        key, _, value = token.partition("=")
        if key == _NAME_KWARG:
            out[_NAME_KWARG] = " ".join([value, *tokens[index + 1 :]]).strip()
            break
        out[key] = value
        index += 1
    return out


class CmdCompanion(DispatchCommand):
    """Manage your bonded companions — bind, release, fight, deploy (#1918).

    Usage:
        companion                             — list active companions + capacity
        companion status                      — (same)
        companion list                        — (same)
        companion bind archetype=<name|id> gift=<name|id> name=<text>
                                              — bind a new companion
        companion release <name|id>           — release a bonded companion
        companion fight <name|id>             — commit a companion into combat
        companion deploy <name|id>            — deploy a companion into a battle

    ``name=`` must be the final token on ``bind`` (it greedily consumes the rest
    of the line so names with spaces work).
    """

    key = "companion"
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        """Route the leading subverb; bare ``companion``/``status``/``list`` shows the hub."""
        raw = (self.args or "").strip()
        if not raw or raw.lower() in _HUB_SUBVERBS:
            self._show_status_hub()
            return
        parts = raw.split(maxsplit=1)
        self._subverb = parts[0].lower()
        self._rest = parts[1].strip() if len(parts) > 1 else ""
        if self._subverb not in _SUBVERBS:
            options = ", ".join(_SUBVERBS)
            self.msg(f"Unknown companion action '{self._subverb}'. Try: {options}.")
            return
        super().func()  # resolve_action_ref + resolve_action_args + dispatch

    def resolve_action_ref(self) -> ActionRef:
        """Build a REGISTRY ActionRef for the parsed subverb."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key=_SUBVERBS[self._subverb])

    def resolve_action_args(self) -> dict[str, Any]:
        """Resolve the subverb's arguments into dispatch kwargs."""
        if self._subverb == _BIND_SUBVERB:
            return self._args_bind(_parse_kwargs(self._rest))
        if self._subverb in _POSITIONAL_SUBVERBS:
            return {"companion_id": self._resolve_companion_id(self._rest)}
        return {}  # all subverbs gated in func(); this path is unreachable

    # -- per-subverb argument resolvers ----------------------------------------

    def _sheet(self) -> Any:
        """Return the caller's CharacterSheet, or raise CommandError if none."""
        sheet = getattr(self.caller, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is None:
            msg = "You have no character sheet."
            raise CommandError(msg)
        return sheet

    @staticmethod
    def _resolve_by_name_or_pk(qs: Any, value: str, *, pk_field: str, name_field: str) -> Any:
        """Resolve *value* (digit → pk lookup, else iexact name) on *qs*.

        Returns the first match or None. The caller validates and raises
        ``CommandError`` with a context-specific message on None.
        """
        if value.isdigit():
            return qs.filter(**{pk_field: int(value)}).first()
        return qs.filter(**{name_field: value}).first()

    def _resolve_archetype(self, value: str) -> Any:
        """Resolve *value* (name iexact or pk) to a CompanionArchetype."""
        from world.companions.models import CompanionArchetype  # noqa: PLC0415

        if not value:
            msg = "Specify an archetype: archetype=<name|id>."
            raise CommandError(msg)
        archetype = self._resolve_by_name_or_pk(
            CompanionArchetype.objects,
            value,
            pk_field="pk",
            name_field="name__iexact",
        )
        if archetype is None:
            msg = f"No companion archetype found for '{value}'."
            raise CommandError(msg)
        return archetype

    def _resolve_owned_gift(self, value: str) -> Any:
        """Resolve *value* (gift name iexact or pk) to a CharacterGift owned by the caller.

        Scopes the lookup to ``CharacterGift.objects.filter(character=sheet)`` so
        the caller can never reference a gift they don't own.
        """
        from world.magic.models.gifts import CharacterGift  # noqa: PLC0415

        if not value:
            msg = "Specify a gift: gift=<name|id>."
            raise CommandError(msg)
        sheet = self._sheet()
        char_gift = self._resolve_by_name_or_pk(
            CharacterGift.objects.filter(character=sheet),
            value,
            pk_field="gift_id",
            name_field="gift__name__iexact",
        )
        if char_gift is None:
            msg = f"You do not own a gift matching '{value}'."
            raise CommandError(msg)
        return char_gift.gift

    def _resolve_companion_id(self, value: str) -> int:
        """Resolve *value* (companion name iexact or pk) to a pk of an active owned companion."""
        from world.companions.models import Companion  # noqa: PLC0415

        value = value.strip()
        if not value:
            msg = f"Specify a companion: companion {self._subverb} <name|id>."
            raise CommandError(msg)
        sheet = self._sheet()
        companion = self._resolve_by_name_or_pk(
            Companion.objects.filter(owner=sheet, released_at__isnull=True),
            value,
            pk_field="pk",
            name_field="name__iexact",
        )
        if companion is None:
            msg = f"No active companion found for '{value}'."
            raise CommandError(msg)
        return companion.pk

    def _args_bind(self, parsed: dict[str, str]) -> dict[str, Any]:
        """Resolve bind kwargs: archetype_id, gift_id, name."""
        archetype = self._resolve_archetype(parsed.get(_ARCHETYPE_KWARG, ""))
        gift = self._resolve_owned_gift(parsed.get(_GIFT_KWARG, ""))
        name = parsed.get(_NAME_KWARG, "").strip()
        if not name:
            msg = "Specify a name: name=<text> (must be the final token)."
            raise CommandError(msg)
        if len(name) > _MAX_NAME_LENGTH:
            msg = "Companion names must be 100 characters or fewer."
            raise CommandError(msg)
        return {
            "archetype_id": archetype.pk,
            "gift_id": gift.pk,
            "name": name,
        }

    # -- status hub ------------------------------------------------------------

    def _show_status_hub(self) -> None:
        """List the caller's active companions + remaining capacity per gift."""
        lines = ["|wCompanion actions|n: bind, release, fight, deploy"]

        sheet = getattr(self.caller, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is None:
            self.msg("\n".join(lines))
            return

        active = self.caller.companions.active()
        if not active:
            lines.append("You have no active companions.")
        else:
            lines.append("Your active companions:")
            lines.extend(
                f"  #{c.pk} — {c.name} ({c.archetype.name}, cost {c.archetype.capacity_cost})"
                for c in active
            )

        lines.extend(self._capacity_lines(sheet))
        self.msg("\n".join(lines))

    def _capacity_lines(self, sheet: Any) -> list[str]:
        """Lines showing remaining Companion Capacity per granting gift."""
        from world.companions.services import (  # noqa: PLC0415
            NoCompanionThreadError,
            companion_capacity,
            used_companion_capacity,
        )

        lines: list[str] = []
        for char_gift in sheet.character_gifts.all():
            gift = char_gift.gift
            try:
                used = used_companion_capacity(sheet, gift)
                total = companion_capacity(sheet, gift)
            except NoCompanionThreadError:
                continue  # gift has no GIFT thread → no capacity to show
            remaining = total - used
            lines.append(f"  {gift.name}: {used}/{total} capacity ({remaining} remaining)")
        return lines
