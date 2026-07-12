"""Defense (bars/ward/alarm) telnet command — the ``defense <subverb>``
namespace (#2177). Mirrors ``CmdLabStation``'s subverb-routing shape
(``commands/crafting_station.py``). No business logic lives here — the
command only parses telnet text and dispatches through
``dispatch_player_action``, the same seam the web ``DefenseInstallViewSet``
uses, reaching ``StartDefenseInstallationAction`` / ``FundRoomWardAction`` in
``actions/definitions/room_features.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef

# Subverb tokens.
_SUBVERB_INSTALL = "install"
_SUBVERB_UPGRADE = "upgrade"
_SUBVERB_FUND = "fund"

# subverb -> registry action key. install/upgrade share one Action — it
# distinguishes the two by whether an active defense already exists at a
# lower level (mirrors CmdLabStation's install/upgrade split, #1234).
_SUBVERBS: dict[str, str] = {
    _SUBVERB_INSTALL: "start_defense_installation",
    _SUBVERB_UPGRADE: "start_defense_installation",
    _SUBVERB_FUND: "fund_room_ward",
}

# Defense-kind telnet tokens.
_KIND_BARS = "bars"
_KIND_WARD = "ward"
_KIND_ALARM = "alarm"

# Defense-kind telnet tokens -> DefenseKind values (world.room_features.constants).
_KIND_TOKENS = {_KIND_BARS: "EXIT_BARS", _KIND_WARD: "ROOM_WARD", _KIND_ALARM: "ROOM_ALARM"}

# Telnet kwarg token keys used by _parse_kwargs / resolve_action_args.
_LEVEL_KWARG = "level"
_AMOUNT_KWARG = "amount"
_EXIT_KWARG = "exit"
_RESONANCE_KWARG = "resonance"
_CONDITION_KWARG = "condition"
_DAMAGE_KWARG = "damage"

_DEFAULT_INSTALL_LEVEL = "1"


def _parse_kwargs(args: str) -> dict[str, str]:
    """Parse ``key=value`` tokens, left to right. Non-kwarg tokens are skipped."""
    out: dict[str, str] = {}
    for token in args.split():
        if "=" not in token:
            continue
        key, _, value = token.partition("=")
        out[key] = value
    return out


class CmdDefense(DispatchCommand):
    """Install, upgrade, or fund an exit/room defense.

    Usage:
        defense                              — status hub
        defense install <bars|ward|alarm> [level=<n>]
        defense install ward level=<n> resonance=<name> [condition=<name>] [damage=<n>]
        defense upgrade <bars|ward|alarm> level=<n>
        defense fund amount=<n>              — fund the room's ward
    """

    key = "defense"
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        """Route the leading subverb; bare ``defense`` shows the status hub."""
        raw = (self.args or "").strip()
        if not raw:
            self._show_status_hub()
            return
        parts = raw.split(maxsplit=1)
        self._subverb = parts[0].lower()
        self._rest = parts[1].strip() if len(parts) > 1 else ""
        if self._subverb not in _SUBVERBS:
            options = ", ".join(sorted(set(_SUBVERBS)))
            self.msg(f"Unknown defense action '{self._subverb}'. Try: {options}.")
            return
        super().func()  # resolve_action_ref + resolve_action_args + dispatch

    def resolve_action_ref(self) -> ActionRef:
        """Build a REGISTRY ActionRef for the parsed subverb."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key=_SUBVERBS[self._subverb])

    def resolve_action_args(self) -> dict[str, Any]:
        """Resolve the subverb's arguments into dispatch kwargs."""
        if self._subverb == _SUBVERB_FUND:
            parsed = _parse_kwargs(self._rest)
            amount_raw = parsed.get(_AMOUNT_KWARG, "")
            if not amount_raw or not amount_raw.isdigit():
                msg = "Usage: defense fund amount=<n>."
                raise CommandError(msg)
            return {"amount": int(amount_raw)}

        tokens = self._rest.split(maxsplit=1)
        if not tokens or tokens[0].lower() not in _KIND_TOKENS:
            msg = f"Usage: defense {self._subverb} <bars|ward|alarm> [level=<n>]."
            raise CommandError(msg)
        kind_key = tokens[0].lower()
        rest = tokens[1] if len(tokens) > 1 else ""
        parsed = _parse_kwargs(rest)

        default_level = _DEFAULT_INSTALL_LEVEL if self._subverb == _SUBVERB_INSTALL else ""
        level_raw = parsed.get(_LEVEL_KWARG, default_level)
        if not level_raw or not level_raw.isdigit():
            msg = f"Usage: defense {self._subverb} {kind_key} level=<n>."
            raise CommandError(msg)

        kwargs: dict[str, Any] = {
            "defense_kind": _KIND_TOKENS[kind_key],
            "target_level": int(level_raw),
        }
        if kind_key == _KIND_BARS:
            exit_obj = self.search_or_raise(
                parsed.get(_EXIT_KWARG, ""),
                location=self.caller.location,
                not_found_msg="Usage: defense install bars level=<n> exit=<name>.",
            )
            kwargs["exit"] = exit_obj
        if kind_key == _KIND_WARD:
            self._resolve_ward_kwargs(parsed, kwargs)
        return kwargs

    @staticmethod
    def _resolve_ward_kwargs(parsed: dict[str, str], kwargs: dict[str, Any]) -> None:
        """Resolve resonance + optional condition/damage for a ward install."""
        resonance_name = parsed.get(_RESONANCE_KWARG, "")
        if not resonance_name:
            msg = "Usage: defense install ward level=<n> resonance=<name>."
            raise CommandError(msg)
        from world.magic.models.affinity import Resonance  # noqa: PLC0415

        resonance = Resonance.objects.filter(name__iexact=resonance_name).first()
        if resonance is None:
            msg = f"No such resonance: {resonance_name}."
            raise CommandError(msg)
        kwargs["resonance"] = resonance

        condition_name = parsed.get(_CONDITION_KWARG, "")
        if condition_name:
            from world.conditions.models import ConditionTemplate  # noqa: PLC0415

            condition = ConditionTemplate.objects.filter(name__iexact=condition_name).first()
            if condition is None:
                msg = f"No such condition: {condition_name}."
                raise CommandError(msg)
            if not condition.category.is_negative:
                msg = "A ward reaction condition must be from a harmful category."
                raise CommandError(msg)
            kwargs["reaction_condition"] = condition

        damage_raw = parsed.get(_DAMAGE_KWARG, "")
        if damage_raw:
            if not damage_raw.isdigit():
                msg = "Damage must be a positive number."
                raise CommandError(msg)
            kwargs["reaction_damage_amount"] = int(damage_raw)

    def _show_status_hub(self) -> None:
        """Show the local room's ward/alarm status, if any."""
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415
        from world.room_features.models import RoomAlarmDetails, RoomWardDetails  # noqa: PLC0415

        lines = ["|wDefense actions|n: install, upgrade, fund"]
        room_profile = None
        if self.caller.location is not None:
            room_profile = RoomProfile.objects.filter(objectdb=self.caller.location).first()
        if room_profile is None:
            self.msg("\n".join(lines))
            return

        ward = RoomWardDetails.objects.filter(room_profile=room_profile).active().first()
        if ward is not None:
            lapsed = " (LAPSED)" if ward.lapsed_at else ""
            lines.append(
                f"A ward stands here: L{ward.level}, reserve {ward.resonance_reserve}{lapsed}"
            )
        alarm = RoomAlarmDetails.objects.filter(room_profile=room_profile).active().first()
        if alarm is not None:
            lines.append(f"An alarm stands here: L{alarm.level}")
        self.msg("\n".join(lines))
