"""Telnet ``gmtable`` command tests (#1505) — thin over world.gm.services.

Authorization parity with the web is the load-bearing part: create/list/members/
invite/kick are table-owner ops; archive + transfer are staff-only.
"""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.gm_tables import CmdGMTable
from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMTableStatus
from world.gm.factories import (
    GMProfileFactory,
    GMTableFactory,
    GMTableMembershipFactory,
)
from world.gm.models import GMTable, GMTableMembership
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory


class GMTableCommandTests(TestCase):
    def _run(self, args: str, account: object) -> str:
        cmd = CmdGMTable()
        cmd.caller = MagicMock()
        cmd.account = account
        cmd.args = args
        cmd.switches = []
        cmd.func()
        return "\n".join(str(c.args[0]) for c in cmd.caller.msg.call_args_list if c.args)

    # -- gating --------------------------------------------------------------

    def test_non_gm_non_staff_is_rejected(self) -> None:
        out = self._run("list", AccountFactory())  # no GM profile, not staff
        assert "Only GMs may manage tables" in out

    def test_unknown_subverb_shows_usage(self) -> None:
        out = self._run("frobnicate", GMProfileFactory().account)
        assert "Usage:" in out

    # -- list / create -------------------------------------------------------

    def test_list_shows_owned_tables(self) -> None:
        profile = GMProfileFactory()
        table = GMTableFactory(gm=profile, name="Round Table")
        out = self._run("", profile.account)  # default subverb
        assert f"#{table.pk}" in out
        assert "Round Table" in out

    def test_create_makes_a_table_owned_by_the_gm(self) -> None:
        profile = GMProfileFactory()
        out = self._run("create Heroes Guild=Weekly romp", profile.account)
        table = GMTable.objects.get(name="Heroes Guild")
        assert table.gm == profile
        assert table.description == "Weekly romp"
        assert f"#{table.pk}" in out

    # -- members / invite / kick --------------------------------------------

    def test_members_lists_active_members(self) -> None:
        profile = GMProfileFactory()
        table = GMTableFactory(gm=profile)
        membership = GMTableMembershipFactory(table=table)
        out = self._run(f"members {table.pk}", profile.account)
        assert f"membership #{membership.pk}" in out
        assert membership.persona.name in out

    def test_invite_adds_a_persona(self) -> None:
        profile = GMProfileFactory()
        table = GMTableFactory(gm=profile)
        persona = PersonaFactory(name="Ser Aiden")
        out = self._run(f"invite {table.pk}=Ser Aiden", profile.account)
        assert GMTableMembership.objects.filter(
            table=table, persona=persona, left_at__isnull=True
        ).exists()
        assert "Ser Aiden" in out

    def test_invite_rejects_a_temporary_persona(self) -> None:
        profile = GMProfileFactory()
        table = GMTableFactory(gm=profile)
        PersonaFactory(name="Masked One", persona_type=PersonaType.TEMPORARY)
        out = self._run(f"invite {table.pk}=Masked One", profile.account)
        assert not GMTableMembership.objects.filter(table=table).exists()
        assert out  # the service's rejection is surfaced to the caller

    def test_invite_to_another_gms_table_is_rejected(self) -> None:
        table = GMTableFactory(gm=GMProfileFactory())
        PersonaFactory(name="Outsider")
        out = self._run(f"invite {table.pk}=Outsider", GMProfileFactory().account)
        assert "not your table" in out

    def test_kick_removes_a_member(self) -> None:
        profile = GMProfileFactory()
        membership = GMTableMembershipFactory(table=GMTableFactory(gm=profile))
        out = self._run(f"kick {membership.pk}", profile.account)
        membership.refresh_from_db()
        assert membership.left_at is not None
        assert "Removed" in out

    def test_kick_at_another_gms_table_is_rejected(self) -> None:
        membership = GMTableMembershipFactory(table=GMTableFactory(gm=GMProfileFactory()))
        out = self._run(f"kick {membership.pk}", GMProfileFactory().account)
        membership.refresh_from_db()
        assert membership.left_at is None
        assert "not at your table" in out

    # -- archive / transfer (staff-only, matching the web IsAdminUser) -------

    def test_archive_is_staff_only(self) -> None:
        profile = GMProfileFactory()  # a GM, but not staff
        table = GMTableFactory(gm=profile)
        out = self._run(f"archive {table.pk}", profile.account)
        assert "staff-only" in out
        table.refresh_from_db()
        assert table.status != GMTableStatus.ARCHIVED

    def test_staff_can_archive(self) -> None:
        table = GMTableFactory()
        out = self._run(f"archive {table.pk}", AccountFactory(is_staff=True))
        table.refresh_from_db()
        assert table.status == GMTableStatus.ARCHIVED
        assert "Archived" in out

    def test_transfer_is_staff_only(self) -> None:
        profile = GMProfileFactory()
        table = GMTableFactory(gm=profile)
        out = self._run(f"transfer {table.pk}={profile.account.username}", profile.account)
        assert "staff-only" in out

    def test_staff_can_transfer_to_another_gm(self) -> None:
        target = GMProfileFactory()
        table = GMTableFactory()
        out = self._run(
            f"transfer {table.pk}={target.account.username}", AccountFactory(is_staff=True)
        )
        table.refresh_from_db()
        assert table.gm == target
        assert "Transferred" in out
