"""Telnet ``gemit`` command (#1450) — the staff/GM push face of the public-reaction center.

A thin wrapper over ``world.narrative.services.broadcast_gemit`` (the same service the web gemit
endpoint calls). Staff broadcast a hand-authored message — verbatim, colour codes and all — to a
chosen *reach*: game-wide, one-or-more societies, or one-or-more organizations. Bodies are never
generated; the sender writes every word. (Player/covenant-targeted story emits are a separate,
non-public tool — out of scope here.)

Staff-only for now (``perm(Admin)``); opening the society/org reaches to a GM permission is a later
refinement (kept as one lock change).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.narrative.constants import GemitReach

if TYPE_CHECKING:
    from world.societies.models import Organization, Society

_USAGE = (
    "Usage:\n"
    "  gemit <message>                          — game-wide\n"
    "  gemit/society <name>[,<name>] = <message> — to those societies' members\n"
    "  gemit/org <name>[,<name>] = <message>     — to those organizations' members"
)


class CmdGemit(ArxCommand):
    """Broadcast a hand-authored gemit to a chosen reach (staff).

    The message is sent verbatim — write it exactly as players should see it, colour codes
    included. Game-wide reaches everyone online; the scoped forms reach only the members of the
    named societies / organizations (multiple, comma-separated).

    Usage:
      gemit <message>
      gemit/society <name>[,<name>] = <message>
      gemit/org <name>[,<name>] = <message>
    """

    key = "gemit"
    locks = "cmd:perm(Admin)"
    help_category = "Staff"
    action = None

    def func(self) -> None:
        try:
            self._run()
        except CommandError as exc:
            self.msg(str(exc))

    def _run(self) -> None:
        switches = set(self.switches or [])
        raw = (self.args or "").strip()
        if not raw:
            raise CommandError(_USAGE)

        if "society" in switches:  # noqa: STRING_LITERAL — Evennia switch name, not a discriminator
            names, body = self._parse_targets(raw)
            societies = self._lookup_society(names)
            self._send(body, reach=GemitReach.SPECIFIED, societies=societies)
            sent = ", ".join(s.name for s in societies)
            self.msg(f"Gemit sent to the members of: |c{sent}|n.")
        elif switches & {"org", "organization"}:  # noqa: STRING_LITERAL — Evennia switch names
            names, body = self._parse_targets(raw)
            organizations = self._lookup_org(names)
            self._send(body, reach=GemitReach.SPECIFIED, organizations=organizations)
            sent = ", ".join(o.name for o in organizations)
            self.msg(f"Gemit sent to the members of: |c{sent}|n.")
        else:
            self._send(raw, reach=GemitReach.GAME_WIDE)
            self.msg("Gemit sent game-wide.")

    def _parse_targets(self, raw: str) -> tuple[list[str], str]:
        if "=" not in raw:
            raise CommandError(_USAGE)
        target_part, body = (part.strip() for part in raw.split("=", 1))
        if not body:
            msg = "The gemit needs a message after the '='."
            raise CommandError(msg)
        names = [name.strip() for name in target_part.split(",") if name.strip()]
        if not names:
            msg = "Name at least one target before the '='."
            raise CommandError(msg)
        return names, body

    def _lookup_society(self, names: list[str]) -> list[Society]:
        from world.societies.models import Society  # noqa: PLC0415

        results = []
        for name in names:
            match = Society.objects.filter(name__iexact=name).first()
            if match is None:
                msg = f"No society named '{name}'."
                raise CommandError(msg)
            results.append(match)
        return results

    def _lookup_org(self, names: list[str]) -> list[Organization]:
        from world.societies.models import Organization  # noqa: PLC0415

        results = []
        for name in names:
            match = Organization.objects.filter(name__iexact=name).first()
            if match is None:
                msg = f"No organization named '{name}'."
                raise CommandError(msg)
            results.append(match)
        return results

    def _send(
        self,
        body: str,
        *,
        reach: str,
        societies: list[Society] | None = None,
        organizations: list[Organization] | None = None,
    ) -> None:
        from world.narrative.services import broadcast_gemit  # noqa: PLC0415

        broadcast_gemit(
            body=body,
            sender_account=self.account,
            reach=reach,
            societies=societies,
            organizations=organizations,
        )
