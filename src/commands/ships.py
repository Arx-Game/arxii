"""Ship telnet command — the ``ship <subverb>`` namespace (#1832 Task 9).

A single command routes the four ship lifecycle verbs through the shared
``dispatch_player_action`` seam — the same REGISTRY path the web will use,
reaching the Actions in ``actions/definitions/ships.py``. No new game logic
lives here; the command only parses telnet text, resolves any named
references to model instances, and dispatches.

``commission_ship`` requires already-resolved ``ShipType``/``Covenant``
instances (not names or ids) — this command resolves them here, the same
contract ``crafting_station.py`` follows for ``feature_kind``/``room_profile``.
``upgrade_ship``/``repair_ship``/``ship_status`` resolve their target ship
inside the Action itself (``_resolve_ship`` — explicit ``ship_id``, else the
actor's current location); this command only forwards an optional
``ship_id`` when the player supplies one.

Mirrors ``CmdSanctum``'s subverb-routing shape (``commands/sanctum.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef

# subverb -> registry action key.
_SUBVERBS: dict[str, str] = {
    "commission": "commission_ship",
    "upgrade": "upgrade_ship",
    "repair": "repair_ship",
    "status": "ship_status",
}

# Bare ``ship status`` (no further tokens) is an alias for the hub.
_STATUS_SUBVERB = "status"

# Telnet kwarg token keys used by _parse_kwargs / resolve_action_args.
_SHIP_TYPE_KWARG = "ship_type"
_NAME_KWARG = "name"
_COVENANT_KWARG = "covenant"
_STAT_KWARG = "stat"
_LEVEL_KWARG = "level"
_SHIP_ID_KWARG = "ship_id"


def _parse_kwargs(args: str) -> dict[str, str]:
    """Parse ``key=value`` tokens, left to right.

    ``name`` greedily consumes the rest of the line so a ship name may
    contain spaces (mirrors ``sanctum.py``'s ``narrative=`` special-case).
    All other values are single whitespace-delimited tokens. Tokens that
    contain no ``=`` are silently skipped (positional leftovers).
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


class CmdShip(DispatchCommand):
    """Commission, upgrade, repair, or check a ship.

    Usage:
        ship                                        — status hub
        ship status [ship_id=<n>]                    — status hub, or a
                                                        specific ship's report
        ship commission ship_type=<name> [covenant=<name>] name=<ship name>
                                                      — commission a new ship
        ship upgrade stat=handling|armament|hull
             level=<n> [ship_id=<n>]                   — raise a ship stat
        ship repair [ship_id=<n>]                      — start repairs

    ``name=`` greedily consumes the rest of the line so a ship name may
    contain spaces — it must come last on the ``commission`` line (mirrors
    ``sanctum homecoming``'s ``narrative=`` placement).
    """

    key = "ship"
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        """Route the leading subverb; bare ``ship``/``ship status`` shows the hub."""
        raw = (self.args or "").strip()
        if not raw or raw.lower() == _STATUS_SUBVERB:
            self._show_status_hub()
            return
        parts = raw.split(maxsplit=1)
        self._subverb = parts[0].lower()
        self._rest = parts[1].strip() if len(parts) > 1 else ""
        if self._subverb not in _SUBVERBS:
            options = ", ".join(_SUBVERBS)
            self.msg(f"Unknown ship action '{self._subverb}'. Try: {options}.")
            return
        super().func()  # resolve_action_ref + resolve_action_args + dispatch

    def resolve_action_ref(self) -> ActionRef:
        """Build a REGISTRY ActionRef for the parsed subverb."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key=_SUBVERBS[self._subverb])

    def resolve_action_args(self) -> dict[str, Any]:
        """Resolve the subverb's arguments into dispatch kwargs."""
        parsed = _parse_kwargs(self._rest)
        handlers = {
            "commission": self._args_commission,
            "upgrade": self._args_upgrade,
            "repair": self._args_optional_ship_id,
            "status": self._args_optional_ship_id,
        }
        handler = handlers.get(self._subverb)
        if handler is not None:
            return handler(parsed)
        return {}  # all subverbs gated in func(); this path is unreachable

    # -- per-subverb argument resolvers ----------------------------------------

    def _require_ship_type(self, name: str) -> Any:
        """Resolve *name* to a ShipType (iexact), or raise CommandError."""
        from world.ships.models import ShipType  # noqa: PLC0415

        ship_type = ShipType.objects.filter(name__iexact=name).first()
        if ship_type is None:
            msg = f"There is no ship type called '{name}'."
            raise CommandError(msg)
        return ship_type

    def _require_covenant(self, name: str) -> Any:
        """Resolve *name* to a Covenant (iexact), or raise CommandError."""
        from world.covenants.models import Covenant  # noqa: PLC0415

        covenant = Covenant.objects.filter(name__iexact=name).first()
        if covenant is None:
            msg = f"There is no covenant called '{name}'."
            raise CommandError(msg)
        return covenant

    def _args_commission(self, parsed: dict[str, str]) -> dict[str, Any]:
        """Resolve commission kwargs: ship_type, name, optional covenant.

        ``ship_type``/``covenant`` are resolved here to model instances —
        ``CommissionShipAction`` requires already-resolved instances, not
        telnet strings. ``name=`` is a greedy token (see ``_parse_kwargs``)
        that consumes the rest of the line, so it must be supplied last —
        any ``ship_type=``/``covenant=`` token after it would be swallowed
        into the ship name instead of parsed as its own kwarg.
        """
        ship_type_raw = parsed.get(_SHIP_TYPE_KWARG, "").strip()
        name = parsed.get(_NAME_KWARG, "").strip()
        if not ship_type_raw or not name:
            msg = "Usage: ship commission ship_type=<name> [covenant=<name>] name=<ship name>."
            raise CommandError(msg)
        kwargs: dict[str, Any] = {
            "ship_type": self._require_ship_type(ship_type_raw),
            "name": name,
        }
        covenant_raw = parsed.get(_COVENANT_KWARG, "").strip()
        if covenant_raw:
            kwargs["covenant"] = self._require_covenant(covenant_raw)
        return kwargs

    def _args_upgrade(self, parsed: dict[str, str]) -> dict[str, Any]:
        """Resolve upgrade kwargs: stat, target_level, optional ship_id."""
        stat = parsed.get(_STAT_KWARG, "").strip().lower()
        level_raw = parsed.get(_LEVEL_KWARG, "")
        if not stat or not level_raw or not level_raw.isdigit():
            msg = "Usage: ship upgrade stat=<handling|armament|hull> level=<n>."
            raise CommandError(msg)
        kwargs: dict[str, Any] = {"stat": stat, "target_level": int(level_raw)}
        kwargs.update(self._args_optional_ship_id(parsed))
        return kwargs

    def _args_optional_ship_id(self, parsed: dict[str, str]) -> dict[str, Any]:
        """Resolve the shared optional ``ship_id`` kwarg (repair/status/upgrade).

        The Action's own ``_resolve_ship`` falls back to the actor's location
        when no ``ship_id`` is given, so this is a pass-through, not a lookup.
        """
        ship_id_raw = parsed.get(_SHIP_ID_KWARG, "")
        if ship_id_raw and ship_id_raw.isdigit():
            return {"ship_id": int(ship_id_raw)}
        return {}

    # -- status hub ------------------------------------------------------------

    def _show_status_hub(self) -> None:
        """Show the local ship's status, if the caller stands aboard one."""
        lines = ["|wShip actions|n: commission, upgrade, repair, status"]
        ship = self._ship_in_room()
        if ship is None:
            lines.append("There is no ship here.")
        else:
            status = " (needs repair)" if ship.needs_repair else ""
            lines.append(
                f"{ship}: hull {ship.effective_hull()}, handling {ship.effective_handling()}, "
                f"armament {ship.effective_armament()}{status}."
            )
        self.msg("\n".join(lines))

    def _ship_in_room(self) -> Any:
        """Return the ShipDetails for the caller's room, or None."""
        from world.ships.models import ShipDetails  # noqa: PLC0415

        location = self.caller.location
        if location is None:
            return None
        return (
            ShipDetails.objects.filter(building__entry_room__objectdb=location)
            .select_related("building__entry_room", "ship_type")
            .first()
        )
