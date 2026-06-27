"""Telnet face of SetTheStageAction (#1498).

Thin command: a staff caller instantiates a ``PositionBlueprint`` into their
current room. Delegates to ``SetTheStageAction`` via ``action.run()`` -- the
same seam the web quick-action (``_set_the_stage_actions``) reaches.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.positioning import SetTheStageAction
from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.areas.positioning.models import PositionBlueprint

_REPLACE_TOKEN = "replace"  # noqa: S105


class CmdSetStage(ArxCommand):
    """Set the stage in your current room -- apply a position blueprint.

    Staff-only. You must be standing in the room to stage.

    Usage:
      setstage                       -- show this room's positions
      setstage <name|id>             -- instantiate <name|id> into this room
      setstage <name|id> replace     -- replace existing positions
    """

    key = "setstage"
    aliases: list[str] = []
    locks = "cmd:perm(Admin)"
    help_category = "Building"
    action = SetTheStageAction()

    def resolve_action_args(self) -> dict[str, Any]:
        """Parse ``<name|id> [replace]`` into SetTheStageAction kwargs."""
        raw = (self.args or "").strip()
        if not raw:
            msg = "Set the stage with which blueprint? (setstage list to see them.)"
            raise CommandError(msg)

        parts = raw.split()
        replace = parts[-1].lower() == _REPLACE_TOKEN
        if replace:
            parts = parts[:-1]

        if not parts:
            msg = "Set the stage with which blueprint? (setstage list to see them.)"
            raise CommandError(msg)

        blueprint = self.resolve_by_name_or_id(
            PositionBlueprint,
            " ".join(parts),
            not_found_msg="No such blueprint. (setstage list to see them.)",
        )
        return {"blueprint_id": blueprint.pk, "replace": replace}
