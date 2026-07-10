"""Telnet face of SetSituationAction (#1895).

Thin command: a JUNIOR-tier-or-higher GM (or staff) caller instantiates a
SituationTemplate into their current room. Delegates to SetSituationAction
via action.run() -- the same seam the web quick-action would reach. The
command lock is ``cmd:all()`` -- real authorization lives entirely in the
Action's ``MinimumGMLevelPrerequisite`` (#2117).

``setsituation find <term>`` (#2127) extends the same command with a
STARTING-tier-or-higher browse mode, mirroring ``gm check find``'s shape
(#2118): delegates to ``FindSituationAction`` instead of instantiating
anything.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.gm_catalog import FindSituationAction
from actions.definitions.situations import SetSituationAction
from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.mechanics.models import SituationTemplate

_FIND_SUBVERB = "find"


class CmdSetSituation(ArxCommand):
    """Instantiate an authored Situation in your current room, or browse the catalog.

    Requires JUNIOR-tier GM trust or higher (or staff) to instantiate. You must
    be standing in the room to trigger it. Browsing (``find``) only requires
    STARTING-tier GM trust or higher -- it mutates nothing.

    Usage:
      setsituation <name|id>       -- instantiate <name|id> into this room
      setsituation find <term>     -- browse situations/kinds matching <term>
    """

    key = "setsituation"
    aliases: list[str] = []
    locks = "cmd:all()"
    help_category = "Building"
    action = SetSituationAction()
    find_action = FindSituationAction()

    def _execute(self) -> None:
        raw = (self.args or "").strip()
        tokens = raw.split(maxsplit=1)
        if tokens and tokens[0].lower() == _FIND_SUBVERB:
            query = tokens[1].strip() if len(tokens) > 1 else ""
            result = self.find_action.run(actor=self.caller, query=query)
            if result.message:
                self.msg(result.message)
            return
        super()._execute()

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
