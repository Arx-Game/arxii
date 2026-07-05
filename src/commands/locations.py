"""Telnet ``room`` command family — the room editor (#1470) + Room Builder (#670).

One namespace command (key ``room``, aliases ``build`` + the legacy
``manageroom``) routes a switch to the matching Action — the same seam the web
action-dispatch uses. Permissions are per-operation by *relationship* (owner
structural / tenant redescribe), gated in the actions + services; no business
logic lives here.

Grammar (each verb is a small single-purpose command — the ratified incremental
rhythm, no monster one-liner):

  room/dig <direction>=<name> [like=<room>] [size=<tier>]
  room/name <new name>            room/desc <description>
  room/size <tier>                room/public <yes|no>
  room/addexit <room>=<there>,<back>
  room/removeexit <exit>          room/renameexit <exit>=<new name>
  room/drop confirm               room/map [floor]
  room/home                       room/tenant <character>
  room/evict <character>          room/extend <units>
  room/decorate <template> [here]         room/style <style name>
  room/renovate <kind name|id>
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand
from commands.exceptions import CommandError

_USAGE = (
    "Usage:\n"
    "  room/dig <direction>=<name> [like=<room>] [size=<tier>]\n"
    "  room/name <new name>  ·  room/desc <text>  ·  room/public <yes|no>\n"
    "  room/size <tier>  ·  room/drop confirm  ·  room/map [floor]\n"
    "  room/addexit <room>=<there>,<back>  ·  room/removeexit <exit>\n"
    "  room/renameexit <exit>=<new name>\n"
    "  room/home  ·  room/tenant <character>  ·  room/evict <character>\n"
    "  room/extend <units>  ·  room/decorate <template> [here]\n"
    "  room/style <style name>  ·  room/fixture <kind>  ·  room/removefixture <kind>\n"
    "  room/renovate <kind name|id>"
)

_AFFIRMATIVE = frozenset({"yes", "y", "true", "on", "1", "public"})


def _split_trailing_kwargs(text: str, keys: tuple[str, ...]) -> tuple[str, dict[str, str]]:
    """Pull trailing ``key=value`` tokens off free text (values may hold spaces)."""
    found: dict[str, str] = {}
    remainder = text
    changed = True
    while changed:
        changed = False
        for key in keys:
            marker = f" {key}="
            idx = remainder.lower().rfind(marker)
            if idx != -1:
                value = remainder[idx + len(marker) :].strip()
                candidate = remainder[:idx].rstrip()
                # Only strip it when the value itself contains no other marker.
                if value and not any(f" {k}=" in f" {value.lower()}" for k in keys):
                    found[key] = value
                    remainder = candidate
                    changed = True
    return remainder.strip(), found


class CmdRoom(ArxCommand):
    """Shape and manage rooms — dig, describe, resize, connect, and call one home.

    Owners restructure; tenants redescribe the room they live in. See
    ``help room`` for the full grammar.
    """

    key = "room"
    aliases = ("build", "manageroom")
    locks = "cmd:all()"
    help_category = "Building"
    action = None  # routes to multiple actions

    def func(self) -> None:
        try:
            self._dispatch()
        except CommandError as err:
            self.msg(str(err))

    def _dispatch(self) -> None:
        switches = {s.lower() for s in (self.switches or [])}
        args = (self.args or "").strip()
        handlers = {
            "dig": self._dig,
            "name": lambda a: self._edit(name=a, error="Give the new room name."),
            "desc": lambda a: self._edit(description=a, error="Give the new description."),
            "description": lambda a: self._edit(description=a, error="Give the new description."),
            "public": self._public,
            "size": lambda a: self._run("resize_room", size=a),
            "drop": self._drop,
            "addexit": self._addexit,
            "removeexit": lambda a: self._run("unlink_rooms", exit=a),
            "renameexit": self._renameexit,
            "map": self._map,
            "home": lambda a: self._run("set_primary_home"),  # noqa: ARG005
            "tenant": self._tenant,
            "evict": self._evict,
            "extend": lambda a: self._run("start_building_extension", added_budget=a),
            "decorate": self._decorate,
            "style": lambda a: self._run("set_building_style", style=a),
            "renovate": lambda a: self._run("start_building_renovation", target_kind=a),
            "fixture": lambda a: self._run("place_room_fixture", kind=a),
            "removefixture": lambda a: self._run("remove_room_fixture", kind=a),
        }
        for switch in switches:
            handler = handlers.get(switch)
            if handler is not None:
                handler(args)
                return
        raise CommandError(_USAGE)

    def _public(self, args: str) -> None:
        if not args:
            msg = "Use 'room/public <yes|no>'."
            raise CommandError(msg)
        self._edit(is_public=args.lower() in _AFFIRMATIVE, error="")

    # ------------------------------------------------------------------
    # Verb handlers — parse, then run the matching Action.

    def _run(self, action_key: str, **kwargs: Any) -> None:
        from actions.registry import get_action  # noqa: PLC0415

        action = get_action(action_key)
        result = action.run(actor=self.caller, **kwargs)
        self.msg(result.message)

    def _edit(self, *, error: str, **kwargs: Any) -> None:
        supplied = {k: v for k, v in kwargs.items() if v != ""}
        if not supplied and error:
            raise CommandError(error)
        self._run("edit_room", **supplied)

    def _dig(self, args: str) -> None:
        if "=" not in args:
            msg = "Usage: room/dig <direction>=<name> [like=<room>] [size=<tier>]"
            raise CommandError(msg)
        direction, rest = args.split("=", 1)
        name, extra = _split_trailing_kwargs(rest.strip(), ("like", "size"))
        if not name:
            msg = "The new room needs a name."
            raise CommandError(msg)
        self._run(
            "dig_room",
            direction=direction.strip(),
            name=name,
            like=extra.get("like", ""),
            size=extra.get("size", ""),
        )

    def _drop(self, args: str) -> None:
        if args.strip().lower() != "confirm":  # noqa: STRING_LITERAL
            msg = (
                "This removes the room you're standing in (contents and everyone "
                "here move to the entry room). Type 'room/drop confirm' to proceed."
            )
            raise CommandError(msg)
        self._run("remove_room")

    def _addexit(self, args: str) -> None:
        if "=" not in args:
            msg = "Usage: room/addexit <room>=<exit name there>,<exit name back>"
            raise CommandError(msg)
        to_name, names = args.split("=", 1)
        there, _, back = names.partition(",")
        if not back.strip():
            msg = "Give both exit names: room/addexit <room>=<there>,<back>"
            raise CommandError(msg)
        self._run(
            "link_rooms",
            to=to_name.strip(),
            name_there=there.strip(),
            name_back=back.strip(),
        )

    def _renameexit(self, args: str) -> None:
        if "=" not in args:
            msg = "Usage: room/renameexit <exit>=<new name>"
            raise CommandError(msg)
        exit_name, new_name = args.split("=", 1)
        self._run("rename_exit", exit=exit_name.strip(), name=new_name.strip())

    def _map(self, args: str) -> None:
        from world.buildings.map_render import render_building_map  # noqa: PLC0415
        from world.buildings.room_services import building_for_room  # noqa: PLC0415

        room = self.caller.location
        building = building_for_room(room) if room is not None else None
        if building is None:
            msg = "You're not inside a building."
            raise CommandError(msg)
        try:
            floor = int(args) if args.strip() else 0
        except ValueError:
            floor = 0
        self.msg(render_building_map(building, floor=floor))

    def _active_persona_of(self, char_name: str) -> Any:
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        target = self.caller.search(char_name)
        if not target:
            msg = f"Could not find '{char_name}'."
            raise CommandError(msg)
        sheet = getattr(target, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is None:
            msg = f"'{char_name}' has no character sheet."
            raise CommandError(msg)
        return active_persona_for_sheet(sheet)

    def _tenant(self, args: str) -> None:
        if not args:
            msg = "Usage: room/tenant <character>"
            raise CommandError(msg)
        persona = self._active_persona_of(args)
        self._run("assign_room_tenant", tenant_persona_id=persona.pk)

    def _evict(self, args: str) -> None:
        from django.db.models import Q  # noqa: PLC0415
        from django.utils import timezone  # noqa: PLC0415

        from evennia_extensions.models import RoomProfile  # noqa: PLC0415
        from world.locations.models import LocationTenancy  # noqa: PLC0415

        if not args:
            msg = "Usage: room/evict <character>"
            raise CommandError(msg)
        persona = self._active_persona_of(args)
        room = self.caller.location
        try:
            profile = room.room_profile if room is not None else None
        except RoomProfile.DoesNotExist:
            profile = None
        if profile is None:
            msg = "You're not in a room."
            raise CommandError(msg)
        now = timezone.now()
        tenancy = (
            LocationTenancy.objects.filter(room_profile=profile, tenant_persona=persona)
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
            .first()
        )
        if tenancy is None:
            msg = f"{persona} holds no tenancy here."
            raise CommandError(msg)
        self._run("end_room_tenancy", tenancy_id=tenancy.pk)

    def _decorate(self, args: str) -> None:
        from world.buildings.models import ProjectTemplate  # noqa: PLC0415

        if not args:
            msg = "Usage: room/decorate <template> [here]"
            raise CommandError(msg)
        target_room = False
        if args.lower().endswith(" here"):
            target_room = True
            args = args[: -len(" here")].strip()
        template = ProjectTemplate.objects.filter(name__iexact=args).first()
        if template is None and args.isdigit():
            template = ProjectTemplate.objects.filter(pk=int(args)).first()
        if template is None:
            msg = f"No decoration template named '{args}'."
            raise CommandError(msg)
        self._run("commission_decoration", template_id=template.pk, target_room=target_room)


# Back-compat import target — older cmdset registrations referenced CmdManageRoom.
CmdManageRoom = CmdRoom
