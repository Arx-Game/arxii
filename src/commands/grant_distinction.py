"""CmdGrantDistinction — GM command for post-CG distinction add/remove (#2037, #2628).

For story-earned moments where a GM adds or removes a catalog Distinction on
a character. Thin telnet face of ``GMAwardDistinctionAction``
(``actions/definitions/distinctions.py``), which goes through the
SheetUpdateRequest framework — XP is charged on the sign-based model (beneficial
costs to add, detrimental costs to remove). Requires JUNIOR-tier GM trust or
higher (or staff) — gated by the Action's ``MinimumGMLevelPrerequisite``.
The command lock is ``cmd:all()``; real authorization lives entirely in the
Action. Mirrors ``CmdGrantItem`` (``commands/grant_item.py``).
"""

from __future__ import annotations

from typing import Any

from actions.definitions.distinctions import GMAwardDistinctionAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

_USAGE = "Usage: grant_distinction <character>=<distinction slug>[,rank]"
_USAGE_REMOVE = "Usage: grant_distinction/remove <character>=<distinction slug>"
_REMOVE_ACTION = "remove"


class CmdGrantDistinction(ArxCommand):
    """Award or remove a catalog Distinction on a character (GM).

    Grants the named distinction at rank 1 (or the given rank); a character
    who already holds it advances one rank instead. ``/remove`` sheds a
    held distinction. Catalog-only — the slug must name an existing active
    Distinction.

    XP is charged on the sign-based model: beneficial distinctions cost XP
    to add and are free to remove; detrimental distinctions are free to add
    and cost XP to remove.

    Requires JUNIOR-tier GM trust or higher (or staff).

    Usage:
      grant_distinction <character>=<distinction slug>[,rank]
      grant_distinction/remove <character>=<distinction slug>
    """

    key = "grant_distinction"
    aliases = ["grantdistinction"]
    locks = "cmd:all()"
    help_category = "Staff"
    action = GMAwardDistinctionAction()

    def resolve_action_args(self) -> dict[str, Any]:
        raw = (self.args or "").strip()
        if "=" not in raw:
            if _REMOVE_ACTION in (self.switches or []):  # noqa: STRING_LITERAL
                raise CommandError(_USAGE_REMOVE)
            raise CommandError(_USAGE)
        name, spec = (part.strip() for part in raw.split("=", 1))
        if not name or not spec:
            raise CommandError(_USAGE)

        args: dict[str, Any] = {"target_name": name}
        if _REMOVE_ACTION in (self.switches or []):  # noqa: STRING_LITERAL
            args["action"] = _REMOVE_ACTION
            args["distinction_slug"] = spec
            return args

        if "," in spec:
            slug, rank_raw = (part.strip() for part in spec.rsplit(",", 1))
            if not slug:
                raise CommandError(_USAGE)
            try:
                rank = int(rank_raw)
            except ValueError:
                msg = "rank must be a whole number."
                raise CommandError(msg) from None
            args["rank"] = rank
        else:
            slug = spec
        args["distinction_slug"] = slug
        return args
