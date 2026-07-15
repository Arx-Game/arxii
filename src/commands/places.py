"""Places telnet command — the ``places`` namespace (#1866).

Bare ``places`` lists active Places in the caller's current room. ``places
join <name>`` resolves a Place by name scoped to the caller's room (telnet
has no pk to reference, and joining a Place elsewhere makes no spatial
sense). ``places leave`` leaves whichever Place the caller's active persona
currently occupies.
"""

from __future__ import annotations

from actions.definitions.places import JoinPlaceAction, LeavePlaceAction
from commands.command import ArxCommand
from commands.exceptions import CommandError


class CmdPlaces(ArxCommand):
    """Join or leave a Place — a named sub-location within your current room.

    Usage:
        places
        places join <name>
        places leave
    """

    key = "places"
    locks = "cmd:all()"

    def func(self) -> None:
        raw = (self.args or "").strip()
        if not raw:
            self._list_places()
            return
        parts = raw.split(maxsplit=1)
        subverb = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""
        handler = {
            "join": lambda: self._do_join(rest),
            "leave": lambda: self._do_leave(),
        }.get(subverb)
        if handler is None:
            self.msg("Usage: places | places join <name> | places leave.")
            return
        try:
            handler()
        except CommandError as err:
            self.msg(str(err))
            self.msg(command_error={"error": str(err), "command": self.raw_string or ""})

    def _list_places(self) -> None:
        from world.scenes.constants import PlaceStatus  # noqa: PLC0415
        from world.scenes.place_models import Place  # noqa: PLC0415

        room = self.caller.location
        if room is None:
            self.msg("You aren't anywhere.")
            return
        places = list(Place.objects.filter(room=room, status=PlaceStatus.ACTIVE).order_by("name"))
        if not places:
            self.msg("There are no places here.")
            return
        lines = ["Places here:"]
        lines.extend(f"  {p.name}" for p in places)
        self.msg("\n".join(lines))

    def _do_join(self, name: str) -> None:
        from world.scenes.constants import PlaceStatus  # noqa: PLC0415
        from world.scenes.place_models import Place  # noqa: PLC0415

        if not name:
            msg = "Join which place?"
            raise CommandError(msg)
        room = self.caller.location
        place = Place.objects.filter(
            room=room, status=PlaceStatus.ACTIVE, name__iexact=name
        ).first()
        if place is None:
            msg = f"No such place here: '{name}'."
            raise CommandError(msg)
        result = JoinPlaceAction().run(actor=self.caller, place=place)
        if result.message:
            self.msg(result.message)

    def _do_leave(self) -> None:
        from world.scenes.place_models import PlacePresence  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        sheet = self.caller.character_sheet
        if sheet is None:
            msg = "No active character."
            raise CommandError(msg)
        persona = active_persona_for_sheet(sheet)
        presence = PlacePresence.objects.filter(persona=persona).select_related("place").first()
        if presence is None:
            msg = "You aren't at a place."
            raise CommandError(msg)
        result = LeavePlaceAction().run(actor=self.caller, place=presence.place)
        if result.message:
            self.msg(result.message)
