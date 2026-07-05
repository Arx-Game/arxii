"""Telnet face of SetSituationAction (#1895).

Thin command: a staff caller instantiates a SituationTemplate into their
current room. Delegates to SetSituationAction via action.run() -- the same
seam the web quick-action would reach.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.situations import SetSituationAction
from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.mechanics.models import SituationTemplate


class CmdSetSituation(ArxCommand):
    """Instantiate an authored Situation in your current room.

    Staff-only. You must be standing in the room to trigger it.

    Usage:
      setsituation <name|id>    -- instantiate <name|id> into this room
    """

    key = "setsituation"
    aliases: list[str] = []
    locks = "cmd:perm(Admin)"
    help_category = "Building"
    action = SetSituationAction()

    def resolve_action_args(self) -> dict[str, Any]:
        """Parse ``<name|id>`` into SetSituationAction kwargs."""
        raw = (self.args or "").strip()
        if not raw:
            msg = "Set which situation? (setsituation <name|id>)"
            raise CommandError(msg)

        template = self.resolve_by_name_or_id(
            SituationTemplate,
            raw,
            not_found_msg="No such situation template.",
        )
        return {"situation_template_id": template.pk}
