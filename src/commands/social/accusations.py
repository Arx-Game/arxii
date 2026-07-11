"""Telnet face of the frame-job mint surface (#1825).

``CmdAccuse`` (``accuse <character> = <claim>``) is a thin ``ArxCommand`` over
``MintAccusationAction`` (key ``mint_accusation``) — the same seam the web will dispatch
through. It resolves the co-located target to their active persona and passes the claim; the
Action owns the consent gate + the mint. No business logic in the command.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.accusations import MintAccusationAction
from commands.command import ArxCommand
from commands.exceptions import CommandError


class CmdAccuse(ArxCommand):
    """Manufacture a false scandal against another character.

    Only works against someone who has opened themselves to antagonism (their consent
    settings). Falsity is emergent — a leaked accusation mints heat and reputation like a
    true one until disproven.

    Usage:
        accuse <character> = <the claim>
    """

    key = "accuse"
    locks = "cmd:all()"
    action = MintAccusationAction()

    def resolve_action_args(self) -> dict[str, Any]:
        raw = (self.args or "").strip()
        name, sep, claim = raw.partition("=")
        name, claim = name.strip(), claim.strip()
        if not sep or not name or not claim:
            usage = "Usage: accuse <character> = <the claim>"
            raise CommandError(usage)

        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        target = self.search_or_raise(name)
        sheet = getattr(target, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is None:
            no_identity = f"{target} has no character identity."
            raise CommandError(no_identity)
        persona = active_persona_for_sheet(sheet)
        return {"target_persona_id": persona.pk, "content": claim}
