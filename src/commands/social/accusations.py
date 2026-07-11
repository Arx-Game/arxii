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

    With ``/crime`` you name a specific crime kind: where the law where you stand
    criminalizes it, the accusation draws pursuit heat onto your target, not just gossip.
    This files a *wild* accusation — a claim with no real crime underneath, so it's the
    fragile, easily-refuted kind.

    Usage:
        accuse <character> = <the claim>
        accuse/crime <character> = <crime-kind> : <the claim>
    """

    key = "accuse"
    locks = "cmd:all()"
    action = MintAccusationAction()

    def resolve_action_args(self) -> dict[str, Any]:
        raw = (self.args or "").strip()
        name, sep, rest = raw.partition("=")
        name, rest = name.strip(), rest.strip()
        is_crime = "crime" in self.switches

        crime_slug = ""
        if is_crime:
            crime_slug, csep, claim = rest.partition(":")
            crime_slug, claim = crime_slug.strip(), claim.strip()
            if not sep or not name or not csep or not crime_slug or not claim:
                usage = "Usage: accuse/crime <character> = <crime-kind> : <the claim>"
                raise CommandError(usage)
        else:
            claim = rest
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
        args: dict[str, Any] = {"target_persona_id": persona.pk, "content": claim}
        if is_crime:
            args["crime_kind_slug"] = crime_slug
        return args
