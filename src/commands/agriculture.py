"""Telnet face of food collection (#2237).

Thin command: ``harvest`` delegates to the REGISTRY ``CollectFoodAction``,
which resolves the Field in the caller's current room and lands its food into
the domain stockpile. Same seam the web ``CollectFoodView`` dispatches through.
"""

from __future__ import annotations

from typing import ClassVar

from actions.definitions.collect_food import CollectFoodAction
from commands.command import ArxCommand


class CmdHarvest(ArxCommand):
    """Collect the food a field here has grown into your domain's stores.

    Stand where a field is. Collection rolls a check — a bad roll loses some
    (or all) of the haul, and a full granary caps what lands.

    Usage:
      harvest
    """

    key = "harvest"
    aliases: ClassVar[list[str]] = []
    locks = "cmd:all()"
    help_category = "General"
    action = CollectFoodAction()
