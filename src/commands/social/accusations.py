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

# The switch that routes a bare accusation into the criminal (heat-bearing) path.
CRIME_SWITCH = "crime"
# The switch that attacks an existing accusation's credibility (the defense, #1825).
REFUTE_SWITCH = "refute"


class CmdAccuse(ArxCommand):
    """Manufacture a false scandal against another character — or pick one apart.

    Only works against someone who has opened themselves to antagonism (their consent
    settings). Falsity is emergent — a leaked accusation mints heat and reputation like a
    true one until disproven.

    With ``/crime`` you name a specific crime kind: where the law where you stand
    criminalizes it, the accusation draws pursuit heat onto your target, not just gossip.
    This files a *wild* accusation — a claim with no real crime underneath, so it's the
    fragile, easily-refuted kind.

    With ``/refute`` you attack a manufactured scandal you've come into, at a social
    hub — anyone may defend the accused; no consent needed. Bare ``accuse/refute``
    lists the scandals you could dispute. One attempt each.

    Usage:
        accuse <character> = <the claim>
        accuse/crime <character> = <crime-kind> : <the claim>
        accuse/refute [<#>]
    """

    key = "accuse"
    locks = "cmd:all()"
    action = MintAccusationAction()

    def _execute(self) -> None:
        if REFUTE_SWITCH in self.switches:
            self._refute((self.args or "").strip())
            return
        super()._execute()

    def _refutable_secrets(self) -> list[Any]:
        """The ACCUSATION secrets this character has come into (recent first)."""
        from world.roster.models import RosterEntry  # noqa: PLC0415
        from world.secrets.constants import SecretProvenance  # noqa: PLC0415
        from world.secrets.services import known_secrets_for  # noqa: PLC0415

        sheet = self.caller.character_sheet
        if sheet is None:
            return []
        try:
            entry = sheet.roster_entry
        except RosterEntry.DoesNotExist:
            return []
        held = known_secrets_for(entry).filter(secret__provenance=SecretProvenance.ACCUSATION)
        return [knowledge.secret for knowledge in held]

    def _refute(self, arg: str) -> None:
        from actions.definitions.accusations import RefuteAccusationAction  # noqa: PLC0415

        secrets = self._refutable_secrets()
        if not arg:
            if not secrets:
                self.msg("You hold no manufactured scandals worth disputing.")
                return
            lines = ["|wScandals you could refute:|n"]
            lines += [f"  {index}. {secret.content}" for index, secret in enumerate(secrets, 1)]
            lines.append("Use |waccuse/refute <#>|n at a social hub to make your case.")
            self.msg("\n".join(lines))
            return
        try:
            position = int(arg) - 1
        except (ValueError, TypeError):
            usage = "Usage: accuse/refute [<#>]"
            raise CommandError(usage) from None
        if not 0 <= position < len(secrets):
            self.msg(f"No scandal #{arg}. See |waccuse/refute|n for the list.")
            return
        result = RefuteAccusationAction().run(self.caller, secret_id=secrets[position].pk)
        self.msg(result.message)

    def resolve_action_args(self) -> dict[str, Any]:
        raw = (self.args or "").strip()
        name, sep, rest = raw.partition("=")
        name, rest = name.strip(), rest.strip()
        is_crime = CRIME_SWITCH in self.switches

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
        sheet = target.character_sheet
        if sheet is None:
            no_identity = f"{target} has no character identity."
            raise CommandError(no_identity)
        persona = active_persona_for_sheet(sheet)
        args: dict[str, Any] = {"target_persona_id": persona.pk, "content": claim}
        if is_crime:
            args["crime_kind_slug"] = crime_slug
        return args
