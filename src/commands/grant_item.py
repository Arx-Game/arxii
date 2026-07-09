"""CmdGrantItem — GM command for ad-hoc narrative item grants (#707, #2117).

For story-earned moments (harvesting a component from a defeated NPC,
finding something at a shrine) where a GM hand-awards a specific touchstone
or reagent, rather than the character purchasing it (no shop/merchant
system exists in this codebase — this IS the acquisition channel). Thin
telnet face of ``GrantItemAction`` (``actions/definitions/items.py``), which
wraps ``world.items.services.narrative_grants
.grant_touchstone_item_to_character`` (the same service the Mission ITEM
reward sink calls). Requires JUNIOR-tier GM trust or higher (or staff) —
gated by the Action's ``MinimumGMLevelPrerequisite`` (#2117). The command
lock is ``cmd:all()``; real authorization lives entirely in the Action.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.items import GrantItemAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

_USAGE = "Usage: grant_item <character>=<item template name>"


class CmdGrantItem(ArxCommand):
    """Grant a specific item template to a character (GM).

    Creates one ItemInstance of the named template, held by the target
    character. Use for story-earned narrative grants (loot, GM rewards) —
    there is no shop system to buy these from instead.

    Requires JUNIOR-tier GM trust or higher (or staff).

    Usage:
      grant_item <character>=<item template name>
    """

    key = "grant_item"
    locks = "cmd:all()"
    help_category = "Staff"
    action = GrantItemAction()

    def resolve_action_args(self) -> dict[str, Any]:
        raw = (self.args or "").strip()
        if "=" not in raw:
            raise CommandError(_USAGE)
        name, template_name = (part.strip() for part in raw.split("=", 1))
        if not name or not template_name:
            raise CommandError(_USAGE)
        return {"target_name": name, "template_name": template_name}
