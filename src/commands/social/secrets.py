"""Telnet ``+secrets`` command (#1334).

The telnet face of the web secret tab — a thin wrapper over ``world.secrets.services``, no
business logic. Your *own* secrets (you own them, so you see them in full) and the secrets you've
learned *about others* (partial — any layer you haven't uncovered reads "Unknown"). On telnet the
caller IS the active character, so the active-character scoping is automatic (no viewer param).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from world.character_sheets.models import CharacterSheet
    from world.roster.models import RosterEntry
    from world.secrets.models import Secret, SecretKnowledge

_NO_IDENTITY = "You have no active character to view secrets with."
_UNKNOWN = "Unknown"
_DEFAULT_SORT = "level"
_ALL = "all"


def _caller_sheet(command: ArxCommand) -> CharacterSheet:
    try:
        return command.caller.sheet_data.primary_persona.character_sheet
    except (AttributeError, ObjectDoesNotExist) as exc:
        raise CommandError(_NO_IDENTITY) from exc


def _caller_roster_entry(command: ArxCommand) -> RosterEntry:
    entry = _caller_sheet(command).roster_entry
    if entry is None:
        raise CommandError(_NO_IDENTITY)
    return entry


class CmdSecrets(ArxCommand):
    """View the secrets you hold.

    Your own secrets — the ones about you — show in full. Secrets you've learned about other
    people show only what you've pieced together; anything you haven't uncovered reads "Unknown".

    Usage:
      +secrets                — your own secrets
      +secrets <character>    — secrets you know about <character>
      +secrets all            — every secret you know about others
      +secrets/<sort> ...     — sort by: level (default), recent, category, subject

    Examples:
      +secrets
      +secrets/recent Crucible
      +secrets/subject all
    """

    key = "+secrets"
    aliases = ["secrets"]
    locks = "cmd:all()"
    action = None

    def func(self) -> None:
        from world.secrets.services import (  # noqa: PLC0415
            SECRET_SORT_KEYS,
            known_secrets_for,
            secrets_owned_by,
        )

        sort = next((s for s in self.switches if s in SECRET_SORT_KEYS), _DEFAULT_SORT)
        arg = (self.args or "").strip()
        try:
            if not arg:
                self._show_own(secrets_owned_by(_caller_sheet(self), sort=sort))
            elif arg.lower() == _ALL:
                held = known_secrets_for(_caller_roster_entry(self), sort=sort)
                self._show_known(held, show_subject=True)
            else:
                target_sheet = self._target_sheet(arg)
                held = known_secrets_for(
                    _caller_roster_entry(self), subject_sheet=target_sheet, sort=sort
                )
                self._show_known(held, show_subject=False)
        except CommandError as exc:
            self.msg(str(exc))

    def _target_sheet(self, name: str) -> CharacterSheet:
        target = self.search_or_raise(name)
        try:
            return target.sheet_data.primary_persona.character_sheet
        except (AttributeError, ObjectDoesNotExist) as exc:
            msg = f"{target} has no character sheet."
            raise CommandError(msg) from exc

    def _show_own(self, secrets: QuerySet[Secret]) -> None:
        lines = ["|wYour secrets:|n"]
        rows = list(secrets)
        if not rows:
            self.msg("You have no secrets of your own.")
            return
        for s in rows:
            cat = s.category.name if s.category_id else _UNKNOWN
            lines.append(f"  |c[{s.get_level_display()}]|n {s.content}")
            lines.append(f"      Category: {cat} | Consequences: {s.consequences or _UNKNOWN}")
        self.msg("\n".join(lines))

    def _show_known(self, held_rows: QuerySet[SecretKnowledge], *, show_subject: bool) -> None:
        rows = list(held_rows)
        if not rows:
            self.msg("You know no secrets about others." if show_subject else "You know none.")
            return
        lines = ["|wSecrets you know:|n"]
        for held in rows:
            secret = held.secret
            cat = secret.category.name if (held.knows_category and secret.category_id) else _UNKNOWN
            cons = (
                secret.consequences
                if (held.knows_consequences and secret.consequences)
                else _UNKNOWN
            )
            about = f" |x(about {secret.subject_sheet.character.db_key})|n" if show_subject else ""
            lines.append(f"  |c[{secret.get_level_display()}]|n{about} {secret.content}")
            lines.append(f"      Category: {cat} | Consequences: {cons}")
        self.msg("\n".join(lines))
