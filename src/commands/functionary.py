"""Telnet ``functionary`` command (#1766) — list, place, or remove room functionaries.

A Functionary is a non-piloted class-1 NPC that anchors a room's gameplay loops (you
``hire`` it to reach its services). Listing is open; placing/removing is staff-only. Thin
over ``world.npc_services.functionaries`` — no business logic here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.npc_services.models import NPCRole

if TYPE_CHECKING:
    from evennia_extensions.models import RoomProfile

_USAGE = (
    "Usage:\n"
    "  functionary                        — list functionaries here\n"
    "  functionary place <role>[=<name>]  — (staff) place a functionary of <role> here\n"
    "  functionary remove <role>          — (staff) remove the <role> functionary here"
)

_STAFF_PERM = "Builder"


class CmdFunctionary(ArxCommand):
    """List, place, or remove the Functionaries standing in your current room (#1766).

    A Functionary is a non-piloted NPC that anchors a room's gameplay loops — ``hire`` it to
    reach its services. ``<role>`` is an ``NPCRole`` name or id; the optional ``=<name>``
    gives the placement its own display name (e.g. 'Old Marta' for a Barkeep role).

    Usage:
      functionary                        — list functionaries here
      functionary place <role>[=<name>]  — (staff) place a functionary of <role> here
      functionary remove <role>          — (staff) remove the <role> functionary here
    """

    key = "functionary"
    locks = "cmd:all()"
    help_category = "Building"

    def func(self) -> None:
        try:
            parts = (self.args or "").strip().split(maxsplit=1)
            verb = parts[0].lower() if parts else "list"
            rest = parts[1].strip() if len(parts) > 1 else ""
            if verb in ("", "list"):  # noqa: STRING_LITERAL — subverb keywords, not discriminators
                self._list()
            elif verb == "place":  # noqa: STRING_LITERAL
                self._place(rest)
            elif verb == "remove":  # noqa: STRING_LITERAL
                self._remove(rest)
            else:
                self.msg(_USAGE)
        except CommandError as err:
            self.msg(str(err))

    def _room_profile(self) -> RoomProfile:
        from world.areas.services import get_room_profile  # noqa: PLC0415

        location = self.caller.location
        if location is None:
            msg = "You are not in a room."
            raise CommandError(msg)
        return get_room_profile(location)

    def _require_staff(self) -> None:
        if not self.caller.check_permstring(_STAFF_PERM):
            msg = "Only staff may place or remove functionaries."
            raise CommandError(msg)

    def _resolve_role(self, query: str) -> NPCRole:
        return self.resolve_by_name_or_id(
            NPCRole, query, not_found_msg="No NPC role by that name or id."
        )

    def _list(self) -> None:
        from world.npc_services.functionaries import functionaries_in_room  # noqa: PLC0415

        names = [f.display_name for f in functionaries_in_room(self._room_profile())]
        if names:
            self.msg("|wFunctionaries here:|n " + ", ".join(names))
        else:
            self.msg("No functionaries are here.")

    def _place(self, rest: str) -> None:
        self._require_staff()
        from world.npc_services.functionaries import place_functionary  # noqa: PLC0415

        role_query, _, name = rest.partition("=")
        role_query = role_query.strip()
        if not role_query:
            msg = "Usage: functionary place <role>[=<name>]"
            raise CommandError(msg)
        role = self._resolve_role(role_query)
        functionary = place_functionary(
            role=role, room=self._room_profile(), name_override=name.strip()
        )
        self.msg(f"Placed {functionary.display_name} ({role.name}) here.")

    def _remove(self, rest: str) -> None:
        self._require_staff()
        from world.npc_services.functionaries import remove_functionary  # noqa: PLC0415

        if not rest:
            msg = "Usage: functionary remove <role>"
            raise CommandError(msg)
        role = self._resolve_role(rest)
        if remove_functionary(role=role, room=self._room_profile()):
            self.msg(f"Removed the {role.name} functionary here.")
        else:
            self.msg(f"No {role.name} functionary is here.")
