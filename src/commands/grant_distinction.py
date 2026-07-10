"""CmdGrantDistinction — GM command for post-CG distinction awards (#2037).

For story-earned moments where a GM hand-awards a catalog Distinction to a
character, or ranks up one they already hold. Thin telnet face of
``GMAwardDistinctionAction`` (``actions/definitions/distinctions.py``), which
wraps ``world.distinctions.services.grant_distinction`` — the single shared
acquisition seam every in-play Distinction source calls. Requires JUNIOR-tier
GM trust or higher (or staff) — gated by the Action's
``MinimumGMLevelPrerequisite``. The command lock is ``cmd:all()``; real
authorization lives entirely in the Action. Mirrors ``CmdGrantItem``
(``commands/grant_item.py``) exactly.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.distinctions import GMAwardDistinctionAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

_USAGE = "Usage: grant_distinction <character>=<distinction slug>[,rank]"


class CmdGrantDistinction(ArxCommand):
    """Award a catalog Distinction to a character, or rank up a held one (GM).

    Grants the named distinction at rank 1 (or the given rank); a character
    who already holds it advances one rank instead (or to the given rank).
    Catalog-only — the slug must name an existing active Distinction; this
    never creates one.

    Requires JUNIOR-tier GM trust or higher (or staff).

    Usage:
      grant_distinction <character>=<distinction slug>[,rank]
    """

    key = "grant_distinction"
    locks = "cmd:all()"
    help_category = "Staff"
    action = GMAwardDistinctionAction()

    def resolve_action_args(self) -> dict[str, Any]:
        raw = (self.args or "").strip()
        if "=" not in raw:
            raise CommandError(_USAGE)
        name, spec = (part.strip() for part in raw.split("=", 1))
        if not name or not spec:
            raise CommandError(_USAGE)

        args: dict[str, Any] = {"target_name": name}
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
