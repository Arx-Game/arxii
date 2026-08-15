"""Telnet command for NPC doorman assignment (#2989).

    doorman              - list active doorman assignments in this room
    doorman assign <npc> - assign the named NPC as doorman
    doorman unassign     - retire the room's active doorman

Only the room's owner can assign/unassign (gated by ``IsRoomOwnerPrerequisite``
on the underlying actions — mirrors ``CmdGuard``). A posted doorman
announces every arrival (``world.npc_services.doorman_services
.announce_arrival``, wired at ``Character.at_post_move``) — announcement
only, no access challenge (see the #2989 spec's Decision 4).
"""

from __future__ import annotations

from commands.command import ArxCommand


class CmdDoorman(ArxCommand):
    """Manage the room's NPC doorman.

    Usage:
        doorman
        doorman assign <npc>
        doorman unassign

    Assigns or removes the room's doorman. Only the room owner may
    assign/unassign.
    """

    key = "doorman"
    aliases = ("doormen",)
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
        }

        if not switches and not args:
            self._run_list()
            return

        if not switches:
            self.msg("Usage: doorman | doorman assign <npc> | doorman unassign")
            return

        switch = next(iter(switches))
        handler = handlers.get(switch)
        if handler is None:
            self.msg("Usage: doorman | doorman assign <npc> | doorman unassign")
            return
        handler(args)

    def _run_list(self) -> None:
        from actions.registry import get_action  # noqa: PLC0415

        action = get_action("list_doorman_assignments")
        result = action.run(self.caller)
        self.msg(result.message)

    def _assign(self, npc_name: str) -> None:
        from actions.registry import get_action  # noqa: PLC0415
        from world.npc_services.functionaries import (  # noqa: PLC0415
            functionary_in_location,
        )

        npc_name = npc_name.strip()
        if not npc_name:
            self.msg("Assign whom? Usage: doorman assign <npc>")
            return

        func = functionary_in_location(self.caller.location, npc_name)
        if func is not None:
            action = get_action("assign_doorman")
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
            action = get_action("assign_doorman")
            result = action.run(self.caller, source_type="npc_asset", npc_id=asset.pk)
            self.msg(result.message)
            return

        self.msg(f"No NPC named '{npc_name}' found here or in your assets.")

    def _unassign(self, args: str) -> None:
        from actions.registry import get_action  # noqa: PLC0415

        action = get_action("unassign_doorman")
        result = action.run(self.caller)
        self.msg(result.message)
