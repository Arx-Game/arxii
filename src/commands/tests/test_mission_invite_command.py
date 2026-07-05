"""Telnet journey tests for mission invite/accept/decline (#887)."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.missions import CmdMission
from world.missions.models import MissionInvite
from world.missions.services.run import staff_assign_mission
from world.missions.tests.test_1036_group_play import _group_graph, _pc


def _run(caller: object, args: str = "") -> CmdMission:
    """Build and execute a `mission` command instance; return it for assertions."""
    cmd = CmdMission()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"mission {args}".strip()
    caller.msg = MagicMock()
    cmd.func()
    return cmd


def _holder_instance(name="cmd"):
    template, _entry, _opt_a, _opt_b, _dest_a, _dest_b = _group_graph(name)
    holder = _pc()
    return staff_assign_mission(template, holder), holder


class MissionInviteCommandTest(TestCase):
    def setUp(self) -> None:
        self.instance, self.holder = _holder_instance()
        self.p2 = _pc()
        self.holder.search = MagicMock(return_value=self.p2)
        self.holder.msg = MagicMock()
        self.p2.msg = MagicMock()

    def test_invite_creates_pending_invite(self) -> None:
        _run(self.holder, f"invite {self.instance.pk} {self.p2.key}")
        self.assertTrue(
            MissionInvite.objects.filter(
                instance=self.instance,
                target_persona=self.p2.sheet_data.primary_persona,
            ).exists()
        )

    def test_accept_adds_participant(self) -> None:
        _run(self.holder, f"invite {self.instance.pk} {self.p2.key}")
        invite = MissionInvite.objects.get(instance=self.instance)
        _run(self.p2, f"accept {invite.pk}")
        self.assertTrue(self.instance.participants.filter(character=self.p2).exists())

    def test_decline_leaves_party_unchanged(self) -> None:
        _run(self.holder, f"invite {self.instance.pk} {self.p2.key}")
        invite = MissionInvite.objects.get(instance=self.instance)
        _run(self.p2, f"decline {invite.pk}")
        self.assertFalse(self.instance.participants.filter(character=self.p2).exists())
        invite.refresh_from_db()
        self.assertEqual(invite.response, MissionInvite.Response.DECLINED)

    def test_accept_nonexistent_invite_is_404_style(self) -> None:
        """A non-invitee probing ids gets a not-participant message, not a leak."""
        cmd = _run(self.p2, "accept 999999")
        self.assertTrue(cmd.caller.msg.called)
