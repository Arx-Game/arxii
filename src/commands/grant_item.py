"""CmdGrantItem — staff command for ad-hoc narrative item grants (#707).

For story-earned moments (harvesting a component from a defeated NPC,
finding something at a shrine) where a GM hand-awards a specific touchstone
or reagent, rather than the character purchasing it (no shop/merchant
system exists in this codebase — this IS the acquisition channel). Thin
over ``world.items.services.narrative_grants.grant_touchstone_item_to_character``
(the same service the Mission ITEM reward sink calls). Staff-only for now
(``perm(Admin)``), mirroring ``gemit``/``demandransom``/``setstage``.
"""

from __future__ import annotations

from commands.command import ArxCommand
from commands.exceptions import CommandError

_USAGE = "Usage: grant_item <character>=<item template name>"


class CmdGrantItem(ArxCommand):
    """Grant a specific item template to a character (staff).

    Creates one ItemInstance of the named template, held by the target
    character. Use for story-earned narrative grants (loot, GM rewards) —
    there is no shop system to buy these from instead.

    Usage:
      grant_item <character>=<item template name>
    """

    key = "grant_item"
    locks = "cmd:perm(Admin)"
    help_category = "Staff"
    action = None

    def func(self) -> None:
        try:
            self._run()
        except CommandError as exc:
            self.msg(str(exc))

    def _run(self) -> None:
        from world.items.models import ItemTemplate  # noqa: PLC0415
        from world.items.services.narrative_grants import (  # noqa: PLC0415
            grant_touchstone_item_to_character,
        )

        raw = (self.args or "").strip()
        if "=" not in raw:
            raise CommandError(_USAGE)
        name, template_name = (part.strip() for part in raw.split("=", 1))
        if not name or not template_name:
            raise CommandError(_USAGE)

        target = self.caller.search(name, global_search=True)
        if target is None:
            return  # search() already messaged the caller.

        sheet = getattr(target, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is None:
            msg = "That is not a character."
            raise CommandError(msg)

        template = ItemTemplate.objects.filter(name__iexact=template_name).first()
        if template is None:
            msg = f"No item template found named '{template_name}'."
            raise CommandError(msg)

        grant_touchstone_item_to_character(
            character_sheet=sheet, template=template, granted_by=self.account
        )
        self.msg(f"Granted '{template.name}' to {target.key}.")
