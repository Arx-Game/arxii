"""Telnet command for NPC servant assignment + pampering ambience (#2989).

    servant                - list active servant assignments in this room
    servant assign <npc>   - assign the named NPC as household servant
    servant unassign       - retire the room's active servant
    servant meal           - have the servant prepare a meal (ambience)
    servant bath           - have the servant draw a bath (ambience + a
                              small fatigue recovery)

Assign/unassign are owner-gated (``IsRoomOwnerPrerequisite``, mirrors
``CmdGuard``); meal/bath are gated like servant fetch (owner/tenant standing
+ an active servant in reach) — any resident with standing may be pampered.
"""

from __future__ import annotations

from commands.command import ArxCommand


class CmdServant(ArxCommand):
    """Manage household servants and ask them for pampering.

    Usage:
        servant
        servant assign <npc>
        servant unassign
        servant meal
        servant bath

    Assigns/removes the room's household servant (owner-only). Any resident
    with standing here may ask the servant for a meal or a bath.
    """

    key = "servant"
    aliases = ("servants",)
    locks = "cmd:all()"
    help_category = "Building"
    action = None  # routes to multiple actions

    def func(self) -> None:
        switches = {s.lower() for s in (self.switches or [])}
        args = (self.args or "").strip()

        handlers = {
            "assign": self._assign,
            "unassign": self._unassign,
            "list": lambda a: self._run_list(),  # noqa: ARG005
            "status": lambda a: self._run_list(),  # noqa: ARG005
            "meal": lambda a: self._prepare(kind="meal"),  # noqa: ARG005
            "bath": lambda a: self._prepare(kind="bath"),  # noqa: ARG005
        }

        if not switches and not args:
            self._run_list()
            return

        # `servant meal`/`servant bath` are also reachable as bare args, not
        # just switches, since they read as verbs a player would type plainly.
        if not switches and args.lower() in ("meal", "bath"):
            self._prepare(kind=args.lower())
            return

        if not switches:
            self.msg("Usage: servant | servant assign <npc> | servant unassign | servant meal|bath")
            return

        switch = next(iter(switches))
        handler = handlers.get(switch)
        if handler is None:
            self.msg("Usage: servant | servant assign <npc> | servant unassign | servant meal|bath")
            return
        handler(args)

    def _run_list(self) -> None:
        from actions.registry import get_action  # noqa: PLC0415

        action = get_action("list_servant_assignments")
        result = action.run(self.caller)
        self.msg(result.message)

    def _assign(self, npc_name: str) -> None:
        from actions.registry import get_action  # noqa: PLC0415
        from world.npc_services.functionaries import (  # noqa: PLC0415
            functionary_in_location,
        )

        npc_name = npc_name.strip()
        if not npc_name:
            self.msg("Assign whom? Usage: servant assign <npc>")
            return

        func = functionary_in_location(self.caller.location, npc_name)
        if func is not None:
            action = get_action("assign_servant")
            result = action.run(self.caller, source_type="functionary", npc_id=func.pk)
            self.msg(result.message)
            return

        from world.assets.models import NPCAsset  # noqa: PLC0415
        from world.scenes.services import (  # noqa: PLC0415
            active_persona_for_sheet,
        )

        persona = active_persona_for_sheet(self.caller.sheet_data)
        asset = NPCAsset.objects.filter(
            promoter_persona=persona,
            asset_persona__name__iexact=npc_name,
        ).first()
        if asset is not None:
            action = get_action("assign_servant")
            result = action.run(self.caller, source_type="npc_asset", npc_id=asset.pk)
            self.msg(result.message)
            return

        self.msg(f"No NPC named '{npc_name}' found here or in your assets.")

    def _unassign(self, args: str) -> None:
        from actions.registry import get_action  # noqa: PLC0415

        action = get_action("unassign_servant")
        result = action.run(self.caller)
        self.msg(result.message)

    def _prepare(self, *, kind: str) -> None:
        from actions.registry import get_action  # noqa: PLC0415

        key = (
            "servant_prepare_meal"
            if kind == "meal"  # noqa: STRING_LITERAL — internal kind discriminator, not a model field
            else "servant_prepare_bath"
        )
        action = get_action(key)
        result = action.run(self.caller)
        self.msg(result.message)
