"""Positions telnet command — the ``position`` namespace (#2005, #3385).

Bare ``position`` lists the caller's current room's staged positions with
their occupants and ADJACENT-reach adjacency, or reports the room as
unstaged. ``position <name>`` resolves a Position by name scoped to the
caller's room (telnet has no pk to reference; case-insensitive exact match,
falling back to a unique prefix match, mirroring ``CmdPlaces``) and
dispatches ``TakePositionAction`` when the caller is not yet placed anywhere,
or ``MoveToPositionAction`` when already placed.

``position/fly`` dispatches ``TakeFlightAction`` and ``position/land``
``LandAction`` (#4663): a character with a flight capability takes off into the
air above where she stands, and comes back down. ``position/pass <name>``
dispatches ``PassHeldGroundAction`` (#4663): roll to get past the enemy holding
that adjacent place, with her best matching approach. ``position/stunt <feature> to
<place>`` dispatches ``PerformStuntAction`` (#4675) for the first stunt she could make
from a feature of that name in her place to that place; the listing names each place's
features.

``position/place <target>=<position name>`` (#3385) dispatches
``GMPlaceInPositionAction`` -- staff/GM-fiat unchecked placement of any
co-located object. No business logic here: the command resolves ``<target>``
via a co-located search and ``<position name>`` via the shared
``resolve_position_by_name`` helper, then hands both to the action, which
re-checks the GM gate and co-location server-side regardless of what this
command validated.
"""

from __future__ import annotations

from actions.definitions.positioning import (
    GMPlaceInPositionAction,
    LandAction,
    MoveToPositionAction,
    PassHeldGroundAction,
    PerformStuntAction,
    TakeFlightAction,
    TakePositionAction,
)
from commands.command import ArxCommand
from commands.exceptions import CommandError
from commands.utils.gm_resolution import resolve_position_by_name

_SWITCH_PLACE = "place"
_SWITCH_FLY = "fly"
_SWITCH_LAND = "land"
_SWITCH_GET_PAST = "pass"
_USAGE_GET_PAST = "Usage: position/pass <position name>"
_SWITCH_STUNT = "stunt"
_USAGE_STUNT = "Usage: position/stunt <feature> to <position name>"
_NO_SUCH_STUNT = "You can't do that from here."
_USAGE_PLACE = "Usage: position/place <target>=<position name>"
_NOT_ANYWHERE = "You aren't anywhere."


class CmdPosition(ArxCommand):
    """Enter or move within your current room's tactical position graph.

    Usage:
        position
        position <name>
        position/place <target>=<position name>
        position/fly
        position/land
        position/pass <name>
        position/stunt <feature> to <name>

    Bare ``position`` lists the places here, who stands in each, and which an enemy
    holds against you in a fight ("held by <name>": stepping in stops you there).

    Switches:
        /fly    take flight into the air above where you stand.
        /land   come down onto the ground below you.
        /pass   roll to get past the enemy holding <name>, a place next to you.
        /stunt  use a feature where you stand (a chandelier, a rope) to reach <name>.
        /place  (GM) set <target> in <position name>.
    """

    key = "position"
    takes_switches = True
    locks = "cmd:all()"

    def func(self) -> None:
        if _SWITCH_PLACE in self.switches:
            try:
                self._do_place()
            except CommandError as err:
                self.msg(str(err))
            return
        if _SWITCH_FLY in self.switches or _SWITCH_LAND in self.switches:
            action = TakeFlightAction() if _SWITCH_FLY in self.switches else LandAction()
            result = action.run(self.caller)
            if result.message:
                self.msg(result.message)
            return

        raw = (self.args or "").strip()
        rolled = {_SWITCH_GET_PAST: self._do_pass, _SWITCH_STUNT: self._do_stunt}
        for switch, handler in rolled.items():
            if switch in self.switches:
                try:
                    handler(raw)
                except CommandError as err:
                    self.msg(str(err))
                return
        if not raw:
            self._list_positions()
            return
        try:
            self._do_position(raw)
        except CommandError as err:
            self.msg(str(err))
            self.msg(command_error={"error": str(err), "command": self.raw_string or ""})

    def _list_positions(self) -> None:
        from world.areas.positioning.models import (  # noqa: PLC0415
            ObjectPosition,
            Position,
            PositionFeature,
        )
        from world.areas.positioning.services import room_position_adjacency  # noqa: PLC0415
        from world.combat.services.held_ground import held_place_holders  # noqa: PLC0415

        room = self.caller.location
        if room is None:
            self.msg(_NOT_ANYWHERE)
            return
        positions = list(Position.objects.filter(room=room).order_by("pk"))
        if not positions:
            self.msg("This room has no positions staged.")
            return

        name_by_id = {p.pk: p.name for p in positions}
        adjacency = {a.position_id: a.adjacent_position_ids for a in room_position_adjacency(room)}
        occupants_by_position: dict[int, list[str]] = {p.pk: [] for p in positions}
        for obj_pos in ObjectPosition.objects.filter(position__room=room).select_related(
            "objectdb", "position"
        ):
            occupants_by_position.setdefault(obj_pos.position_id, []).append(obj_pos.objectdb.key)

        # Places an enemy holds against her in a live fight, read once (#4663).
        holders = held_place_holders(self.caller)
        # Each place's features, read once (#4675).
        features_by_position: dict[int, list[str]] = {}
        for feature in (
            PositionFeature.objects.filter(position__room=room)
            .select_related("feature_type")
            .order_by("pk")
        ):
            features_by_position.setdefault(feature.position_id, []).append(
                feature.feature_type.name
            )

        lines = ["Positions here:"]
        for p in positions:
            occupants = occupants_by_position.get(p.pk, [])
            occupants_text = ", ".join(occupants) if occupants else "empty"
            adjacent_names = [
                name_by_id[pid] for pid in adjacency.get(p.pk, []) if pid in name_by_id
            ]
            adjacent_text = ", ".join(adjacent_names) if adjacent_names else "none"
            held_text = f"; held by {holders[p.pk]}" if p.pk in holders else ""
            features = features_by_position.get(p.pk)
            features_text = f"; features: {', '.join(features)}" if features else ""
            lines.append(
                f"  {p.name} ({p.get_kind_display()}) — "
                f"occupants: {occupants_text}; adjacent: {adjacent_text}{held_text}"
                f"{features_text}"
            )
        self.msg("\n".join(lines))

    def _do_position(self, name: str) -> None:
        from world.areas.positioning.services import position_of  # noqa: PLC0415

        room = self.caller.location
        if room is None:
            msg = _NOT_ANYWHERE
            raise CommandError(msg)
        position = resolve_position_by_name(room, name)

        if position_of(self.caller) is None:
            result = TakePositionAction().run(self.caller, position_id=position.pk)
        else:
            result = MoveToPositionAction().run(self.caller, position_id=position.pk)
        if result.message:
            self.msg(result.message)

    def _do_pass(self, name: str) -> None:
        if not name:
            raise CommandError(_USAGE_GET_PAST)
        room = self.caller.location
        if room is None:
            raise CommandError(_NOT_ANYWHERE)
        position = resolve_position_by_name(room, name)
        result = PassHeldGroundAction().run(self.caller, position_id=position.pk)
        if result.message:
            self.msg(result.message)

    def _do_stunt(self, raw: str) -> None:
        from world.areas.positioning.stunts import stunt_options  # noqa: PLC0415

        feature_name, sep, place_name = raw.partition(" to ")
        feature_name, place_name = feature_name.strip(), place_name.strip()
        if not sep or not feature_name or not place_name:
            raise CommandError(_USAGE_STUNT)
        room = self.caller.location
        if room is None:
            raise CommandError(_NOT_ANYWHERE)
        destination = resolve_position_by_name(room, place_name)
        wanted = feature_name.lower()
        option = next(
            (
                option
                for option in stunt_options(self.caller)
                if option.destination.pk == destination.pk
                and option.feature.feature_type.name.lower() == wanted
            ),
            None,
        )
        if option is None:
            raise CommandError(_NO_SUCH_STUNT)
        result = PerformStuntAction().run(
            self.caller,
            feature_id=option.feature.pk,
            position_id=destination.pk,
            approach_id=option.approach.pk,
        )
        if result.message:
            self.msg(result.message)

    def _do_place(self) -> None:
        args = (self.args or "").strip()
        target_part, sep, position_part = args.partition("=")
        target_name = target_part.strip()
        position_name = position_part.strip()
        if not sep or not target_name or not position_name:
            raise CommandError(_USAGE_PLACE)

        room = self.caller.location
        if room is None:
            msg = _NOT_ANYWHERE
            raise CommandError(msg)

        # Co-located search only -- cannot name anything outside the caller's
        # own room. GMPlaceInPositionAction re-validates co-location regardless.
        target = self.caller.search(target_name, location=room)
        if target is None:
            return  # search() sends its own error message

        position = resolve_position_by_name(room, position_name)

        result = GMPlaceInPositionAction().run(
            self.caller, position_id=position.pk, target_object_id=target.pk
        )
        if result.message:
            self.msg(result.message)
