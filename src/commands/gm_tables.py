"""Telnet surface for GM-table administration (#1505).

The web/React tables module (`frontend/src/tables/`) is the primary, design-target
admin surface; this is the basic telnet parity layer Apostate asked for. Thin over
`world.gm.services` — no business logic here.

Authorization mirrors the web exactly so telnet can't escalate past it:
create / list / members / invite / kick are **table-owner (GM)** operations; archive
and transfer are **staff-only** (the web gates both behind ``IsAdminUser``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.gm.models import GMProfile, GMTable
    from world.scenes.models import Persona

_USAGE = (
    "Usage:\n"
    "  gmtable [list]                  — your tables\n"
    "  gmtable create <name>[=<desc>]  — create a table you own\n"
    "  gmtable members <id>            — list a table's members\n"
    "  gmtable invite <id>=<persona>   — add a persona to your table\n"
    "  gmtable kick <membership-id>    — remove a member\n"
    "  gmtable archive <id>            — archive a table (staff)\n"
    "  gmtable transfer <id>=<account> — reassign a table to another GM (staff)"
)
_NOT_GM = "Only GMs may manage tables."
_NO_PROFILE = "You need a GM profile to own a table."
_STAFF_ONLY_ARCHIVE = "Archiving a table is staff-only."
_STAFF_ONLY_TRANSFER = "Transferring a table is staff-only."
_NO_TABLE = "No such table."
_NOT_YOUR_TABLE = "That is not your table."
_NO_MEMBERSHIP = "No such membership."
_NOT_YOUR_MEMBERSHIP = "That membership is not at your table."
_ALREADY_LEFT = "That member has already left."


class CmdGMTable(ArxCommand):
    """Manage your GM tables from telnet (#1505).

    The web tables panel is the primary surface; this is basic parity. Archive
    and transfer are staff-only, matching the web.

    Usage:
      gmtable [list]
      gmtable create <name>[=<desc>]
      gmtable members <id>
      gmtable invite <id>=<persona>
      gmtable kick <membership-id>
      gmtable archive <id>            (staff)
      gmtable transfer <id>=<account> (staff)
    """

    key = "gmtable"
    locks = "cmd:all()"
    help_category = "GM"
    action = None

    def func(self) -> None:
        try:
            self._run()
        except CommandError as exc:
            self.msg(str(exc))

    def _run(self) -> None:
        gm_profile = self._gm_profile()
        is_staff = bool(self.account and self.account.is_staff)
        if gm_profile is None and not is_staff:
            raise CommandError(_NOT_GM)

        subverb, rest = self._split()
        dispatch = {
            "": self._list,
            "list": self._list,
            "create": self._create,
            "members": self._members,
            "invite": self._invite,
            "kick": self._kick,
            "archive": self._archive,
            "transfer": self._transfer,
        }
        handler = dispatch.get(subverb)
        if handler is None:
            raise CommandError(_USAGE)
        handler(rest, gm_profile, is_staff)

    # -- subverbs ------------------------------------------------------------

    def _list(self, rest: str, gm_profile: GMProfile | None, is_staff: bool) -> None:
        from django.db.models import Count, Q  # noqa: PLC0415

        if gm_profile is None:
            raise CommandError(_NO_PROFILE)
        tables = gm_profile.tables.annotate(
            active_members=Count("memberships", filter=Q(memberships__left_at__isnull=True))
        ).order_by("-created_at")
        if not tables:
            self.msg("You own no tables. Create one with: gmtable create <name>")
            return
        lines = ["|wYour GM tables:|n"]
        lines += [f"  #{t.pk} {t.name} [{t.status}] — {t.active_members} member(s)" for t in tables]
        self.msg("\n".join(lines))

    def _create(self, rest: str, gm_profile: GMProfile | None, is_staff: bool) -> None:
        from world.gm.services import create_table  # noqa: PLC0415

        if gm_profile is None:
            raise CommandError(_NO_PROFILE)
        if not rest:
            raise CommandError(_USAGE)
        name, _, desc = rest.partition("=")
        name, desc = name.strip(), desc.strip()
        if not name:
            raise CommandError(_USAGE)
        table = create_table(gm_profile, name, desc)
        self.msg(f"Created table #{table.pk}: {table.name}")

    def _members(self, rest: str, gm_profile: GMProfile | None, is_staff: bool) -> None:
        from world.gm.models import GMTableMembership  # noqa: PLC0415

        table = self._table_for_management(rest, gm_profile, is_staff)
        memberships = (
            GMTableMembership.objects.filter(table=table, left_at__isnull=True)
            .select_related("persona")
            .order_by("pk")
        )
        if not memberships:
            self.msg(f"Table #{table.pk} ({table.name}) has no active members.")
            return
        lines = [f"|wMembers of #{table.pk} {table.name}:|n"]
        lines += [f"  membership #{m.pk}: {m.persona.name}" for m in memberships]
        self.msg("\n".join(lines))

    def _invite(self, rest: str, gm_profile: GMProfile | None, is_staff: bool) -> None:
        from django.core.exceptions import ValidationError as DjangoValidationError  # noqa: PLC0415

        from world.gm.services import join_table  # noqa: PLC0415

        table_token, persona_token = self._split_eq(rest)
        table = self._table_for_management(table_token, gm_profile, is_staff)
        persona = self._resolve_persona(persona_token)
        try:
            membership = join_table(table, persona)
        except DjangoValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        self.msg(
            f"Added {persona.name} to #{table.pk} ({table.name}) — membership #{membership.pk}."
        )

    def _kick(self, rest: str, gm_profile: GMProfile | None, is_staff: bool) -> None:
        from world.gm.models import GMTableMembership  # noqa: PLC0415
        from world.gm.services import leave_table  # noqa: PLC0415

        membership = (
            GMTableMembership.objects.filter(pk=self._parse_id(rest, "membership id"))
            .select_related("table", "persona")
            .first()
        )
        if membership is None:
            raise CommandError(_NO_MEMBERSHIP)
        if not is_staff and (gm_profile is None or membership.table.gm_id != gm_profile.pk):
            raise CommandError(_NOT_YOUR_MEMBERSHIP)
        if membership.left_at is not None:
            raise CommandError(_ALREADY_LEFT)
        name = membership.persona.name
        table = membership.table
        leave_table(membership)
        self.msg(f"Removed {name} from #{table.pk} ({table.name}).")

    def _archive(self, rest: str, gm_profile: GMProfile | None, is_staff: bool) -> None:
        from world.gm.services import archive_table  # noqa: PLC0415

        if not is_staff:
            raise CommandError(_STAFF_ONLY_ARCHIVE)
        table = self._table_or_error(rest)
        archive_table(table)
        self.msg(f"Archived #{table.pk} ({table.name}).")

    def _transfer(self, rest: str, gm_profile: GMProfile | None, is_staff: bool) -> None:
        from world.gm.models import GMProfile as GMProfileModel  # noqa: PLC0415
        from world.gm.services import transfer_ownership  # noqa: PLC0415

        if not is_staff:
            raise CommandError(_STAFF_ONLY_TRANSFER)
        table_token, account_token = self._split_eq(rest)
        table = self._table_or_error(table_token)
        new_gm = GMProfileModel.objects.filter(account__username__iexact=account_token).first()
        if new_gm is None:
            msg = f"No GM with account '{account_token}'."
            raise CommandError(msg)
        transfer_ownership(table, new_gm)
        self.msg(f"Transferred #{table.pk} ({table.name}) to {account_token}.")

    # -- helpers -------------------------------------------------------------

    def _gm_profile(self) -> GMProfile | None:
        from world.gm.models import GMProfile  # noqa: PLC0415

        account = self.account
        if account is None:
            return None
        try:
            return account.gm_profile
        except GMProfile.DoesNotExist:
            return None

    def _split(self) -> tuple[str, str]:
        raw = (self.args or "").strip()
        if not raw:
            return "", ""
        parts = raw.split(None, 1)
        return parts[0].lower(), (parts[1].strip() if len(parts) > 1 else "")

    def _table_or_error(self, id_token: str) -> GMTable:
        from world.gm.models import GMTable  # noqa: PLC0415

        table = GMTable.objects.filter(pk=self._parse_id(id_token, "table id")).first()
        if table is None:
            raise CommandError(_NO_TABLE)
        return table

    def _table_for_management(
        self, id_token: str, gm_profile: GMProfile | None, is_staff: bool
    ) -> GMTable:
        table = self._table_or_error(id_token)
        if not is_staff and (gm_profile is None or table.gm_id != gm_profile.pk):
            raise CommandError(_NOT_YOUR_TABLE)
        return table

    def _parse_id(self, value: str, label: str) -> int:
        token = (value or "").strip().removeprefix("#")
        if not token.isdigit():
            msg = f"{label.capitalize()} must be a number."
            raise CommandError(msg)
        return int(token)

    def _split_eq(self, rest: str) -> tuple[str, str]:
        if "=" not in (rest or ""):
            raise CommandError(_USAGE)
        left, _, right = rest.partition("=")
        left, right = left.strip(), right.strip()
        if not left or not right:
            raise CommandError(_USAGE)
        return left, right

    def _resolve_persona(self, value: str) -> Persona:
        from world.scenes.models import Persona  # noqa: PLC0415

        token = value.strip().removeprefix("#")
        if token.isdigit():
            persona = Persona.objects.filter(pk=int(token)).first()
        else:
            persona = Persona.objects.filter(name__iexact=value.strip()).first()
        if persona is None:
            msg = f"No persona '{value.strip()}'."
            raise CommandError(msg)
        return persona
