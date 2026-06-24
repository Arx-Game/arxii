"""Telnet ``+grievance`` command (#1429).

The telnet face of the secret-victim grievance prompt — a thin wrapper over
``world.secrets.services.register_secret_grievance``. When a secret you're the wronged party to
becomes known to you, this is how you register your chosen response toward the perpetrator. The
web frontend offers the same choice; both converge on the one service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from world.relationships.models import GrievanceOption
    from world.roster.models import RosterEntry
    from world.secrets.models import Secret

_NO_IDENTITY = "You have no active character to register a grievance with."


def _caller_entry(command: ArxCommand) -> RosterEntry:
    from world.roster.models import RosterEntry  # noqa: PLC0415

    entry = RosterEntry.objects.filter(character_sheet__character=command.caller).first()
    if entry is None:
        raise CommandError(_NO_IDENTITY)
    return entry


class CmdGrievance(ArxCommand):
    """Register a grievance against someone whose secret wronged you.

    When a secret in which you are the wronged party comes to light, you decide how it lands on
    your regard for whoever's responsible — from a quiet hurt to an unforgivable betrayal.

    Usage:
      +grievance                       — secrets you may answer + the available responses
      +grievance <secret> = <response> — register your chosen response (by number or name)

    Examples:
      +grievance
      +grievance 7 = Furious Revelation
    """

    key = "+grievance"
    aliases = ["grievance"]
    locks = "cmd:all()"
    action = None

    def func(self) -> None:
        try:
            entry = _caller_entry(self)
            arg = (self.args or "").strip()
            if "=" not in arg:
                self._show_menu(entry)
                return
            secret_part, option_part = (part.strip() for part in arg.split("=", 1))
            secret = self._resolve_secret(entry, secret_part)
            option = self._resolve_option(option_part)
            self._register(entry, secret, option)
        except CommandError as exc:
            self.msg(str(exc))

    def _grievable_secrets(self, entry: RosterEntry) -> QuerySet[Secret]:
        """Secrets the caller may still answer: a SecretVictim + a knower, not yet grieved."""
        from world.secrets.models import Secret  # noqa: PLC0415

        return (
            Secret.objects.filter(
                victims__persona__character_sheet=entry.character_sheet,
                known_by__roster_entry=entry,
            )
            .exclude(grievances__victim_sheet=entry.character_sheet)
            .distinct()
            .order_by("-created_date")
        )

    def _show_menu(self, entry: RosterEntry) -> None:
        from world.relationships.models import GrievanceOption  # noqa: PLC0415

        secrets = list(self._grievable_secrets(entry))
        if not secrets:
            self.msg("There are no secrets you may answer with a grievance right now.")
            return
        lines = ["|wSecrets you may answer:|n"]
        lines.extend(f"  [{s.pk}] {s.content}" for s in secrets)
        lines.append("|wResponses:|n")
        lines.extend(
            f"  [{o.pk}] {o.label}" for o in GrievanceOption.objects.filter(is_active=True)
        )
        lines.append("Use: +grievance <secret #> = <response # or name>")
        self.msg("\n".join(lines))

    def _resolve_secret(self, entry: RosterEntry, raw: str) -> Secret:
        if not raw.isdigit():
            msg = "Name the secret by its number (see +grievance)."
            raise CommandError(msg)
        secret = self._grievable_secrets(entry).filter(pk=int(raw)).first()
        if secret is None:
            msg = "That is not a secret you may answer with a grievance."
            raise CommandError(msg)
        return secret

    def _resolve_option(self, raw: str) -> GrievanceOption:
        from world.relationships.models import GrievanceOption  # noqa: PLC0415

        options = GrievanceOption.objects.filter(is_active=True)
        option = (
            options.filter(pk=int(raw)).first()
            if raw.isdigit()
            else options.filter(label__iexact=raw).first()
        )
        if option is None:
            msg = "That is not an available response (see +grievance)."
            raise CommandError(msg)
        return option

    def _register(self, entry: RosterEntry, secret: Secret, option: GrievanceOption) -> None:
        from world.secrets.services import SecretError, register_secret_grievance  # noqa: PLC0415

        try:
            register_secret_grievance(roster_entry=entry, secret=secret, option=option)
        except SecretError as exc:
            raise CommandError(exc.user_message) from exc
        self.msg(f"You answer the wrong against you: |c{option.label}|n.")
