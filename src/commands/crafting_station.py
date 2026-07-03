"""Lab station telnet command — the ``station <subverb>`` namespace (#1234).

Mirrors ``CmdSanctum``'s subverb-routing shape. No business logic lives here —
the command only parses telnet text and dispatches through
``dispatch_player_action``, the same seam the web ``LabStationViewSet``
(Task 11) uses, reaching ``StartRoomFeatureProjectAction`` /
``RepairLabStationAction`` in ``actions/definitions/room_features.py``.
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
_SUBVERB_REPAIR = "repair"

# subverb -> registry action key. install/upgrade share one Action — it
# distinguishes the two by whether an active feature instance already exists
# at a lower level (#1234 Decision 7).
_SUBVERBS: dict[str, str] = {
    _SUBVERB_INSTALL: "start_room_feature_project",
    _SUBVERB_UPGRADE: "start_room_feature_project",
    _SUBVERB_REPAIR: "repair_lab_station",
}

# Telnet kwarg token keys used by _parse_kwargs / resolve_action_args.
_LEVEL_KWARG = "level"
_POINTS_KWARG = "points"

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


class CmdLabStation(DispatchCommand):
    """Interact with the Lab crafting station in your current room.

    Usage:
        station                       — status hub
        station install [level=<n>]   — start an install project (default level=1)
        station upgrade level=<n>     — start an upgrade project to level <n>
        station repair points=<n>     — pay coppers to restore durability
    """

    key = "station"
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        """Route the leading subverb; bare ``station`` shows the status hub."""
        raw = (self.args or "").strip()
        if not raw:
            self._show_status_hub()
            return
        parts = raw.split(maxsplit=1)
        self._subverb = parts[0].lower()
        self._rest = parts[1].strip() if len(parts) > 1 else ""
        if self._subverb not in _SUBVERBS:
            options = ", ".join(sorted(set(_SUBVERBS)))
            self.msg(f"Unknown station action '{self._subverb}'. Try: {options}.")
            return
        super().func()  # resolve_action_ref + resolve_action_args + dispatch

    def resolve_action_ref(self) -> ActionRef:
        """Build a REGISTRY ActionRef for the parsed subverb."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key=_SUBVERBS[self._subverb])

    def resolve_action_args(self) -> dict[str, Any]:
        """Resolve the subverb's arguments into dispatch kwargs."""
        from world.room_features.seeds import ensure_lab_kind  # noqa: PLC0415

        parsed = _parse_kwargs(self._rest)
        room_profile = self._require_room_profile()

        if self._subverb == _SUBVERB_REPAIR:
            points_raw = parsed.get(_POINTS_KWARG, "")
            if not points_raw or not points_raw.isdigit():
                msg = "Usage: station repair points=<n>."
                raise CommandError(msg)
            return {"room_profile": room_profile, "restore_points": int(points_raw)}

        default_level = _DEFAULT_INSTALL_LEVEL if self._subverb == _SUBVERB_INSTALL else ""
        level_raw = parsed.get(_LEVEL_KWARG, default_level)
        if not level_raw or not level_raw.isdigit():
            msg = f"Usage: station {self._subverb} level=<n>."
            raise CommandError(msg)
        return {
            "room_profile": room_profile,
            "feature_kind": ensure_lab_kind(),
            "target_level": int(level_raw),
        }

    def _require_room_profile(self) -> Any:
        """Return the RoomProfile for the caller's location, or raise CommandError."""
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415

        if self.caller.location is None:
            msg = "You are not in a room."
            raise CommandError(msg)
        room_profile = RoomProfile.objects.filter(objectdb=self.caller.location).first()
        if room_profile is None:
            msg = "This room has no room profile."
            raise CommandError(msg)
        return room_profile

    def _show_status_hub(self) -> None:
        """Show the local Lab station's status, if one exists in this room."""
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415
        from world.items.crafting.models import LabStationDetails  # noqa: PLC0415
        from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
        from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

        lines = ["|wStation actions|n: install, upgrade, repair"]
        room_profile = None
        if self.caller.location is not None:
            room_profile = RoomProfile.objects.filter(objectdb=self.caller.location).first()
        if room_profile is None:
            self.msg("\n".join(lines))
            return

        instance = (
            RoomFeatureInstance.objects.filter(
                room_profile=room_profile,
                feature_kind__service_strategy=RoomFeatureServiceStrategy.LAB,
            )
            .active()
            .first()
        )
        if instance is None:
            lines.append("There is no Lab station here.")
            self.msg("\n".join(lines))
            return

        station = LabStationDetails.objects.filter(feature_instance=instance).first()
        if station is not None:
            broken = " (BROKEN)" if station.is_broken else ""
            lines.append(
                f"A Lab station stands here: L{instance.level}, "
                f"{station.durability}/{station.max_durability}{broken}"
            )
        self.msg("\n".join(lines))
