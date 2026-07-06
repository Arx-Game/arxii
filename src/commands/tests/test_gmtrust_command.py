"""Tests for the ``gmtrust`` telnet namespace command (#2000, Task 7).

Thin over ``world.gm.services.promote_gm`` / ``gm_evidence_summary`` — the
same services the web ``GMProfileViewSet`` actions call.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.gmtrust import CmdGMTrust
from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMLevelCapFactory, GMProfileFactory
from world.gm.models import GMLevelChange
from world.societies.constants import RenownRisk


def _make_cmd(caller, args: str) -> CmdGMTrust:
    cmd = CmdGMTrust()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"gmtrust {args}".strip()
    return cmd


def _messages(caller: MagicMock) -> list[str]:
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class CmdGMTrustShowTests(TestCase):
    def setUp(self) -> None:
        self.caller = MagicMock()
        self.caller.msg = MagicMock()

    def _run(self, caller, args: str) -> list[str]:
        cmd = _make_cmd(caller, args)
        cmd.func()
        return _messages(caller)

    def test_non_gm_show_says_not_a_gm(self) -> None:
        account = AccountFactory(is_staff=False)
        caller = MagicMock()
        caller.msg = MagicMock()
        caller.account = account

        messages = self._run(caller, "show")

        joined = " ".join(messages)
        self.assertIn("You are not a GM.", joined)

    def test_gm_show_reports_level_and_caps(self) -> None:
        GMLevelCapFactory(
            level=GMLevel.JUNIOR,
            max_beat_risk=RenownRisk.MODERATE,
            allow_custom_stakes=False,
            allow_global_scope_authoring=False,
        )
        profile = GMProfileFactory(level=GMLevel.JUNIOR)
        caller = MagicMock()
        caller.msg = MagicMock()
        caller.account = profile.account

        messages = self._run(caller, "show")

        joined = " ".join(messages)
        self.assertIn(profile.account.username, joined)
        self.assertIn("Junior GM", joined)
        self.assertIn("Moderate", joined)

    def test_show_another_account_requires_staff(self) -> None:
        viewer = AccountFactory(is_staff=False)
        target = GMProfileFactory()
        caller = MagicMock()
        caller.msg = MagicMock()
        caller.account = viewer

        messages = self._run(caller, f"show {target.account.username}")

        joined = " ".join(messages)
        self.assertIn("Only staff", joined)

    def test_staff_can_show_another_accounts_level(self) -> None:
        staff_account = AccountFactory(is_staff=True)
        target = GMProfileFactory(level=GMLevel.GM)
        caller = MagicMock()
        caller.msg = MagicMock()
        caller.account = staff_account

        messages = self._run(caller, f"show {target.account.username}")

        joined = " ".join(messages)
        self.assertIn(target.account.username, joined)

    def test_show_unknown_account_errors(self) -> None:
        staff_account = AccountFactory(is_staff=True)
        caller = MagicMock()
        caller.msg = MagicMock()
        caller.account = staff_account

        messages = self._run(caller, "show nobody-here")

        joined = " ".join(messages)
        self.assertIn("No account named", joined)


class CmdGMTrustEvidenceTests(TestCase):
    def _run(self, caller, args: str) -> list[str]:
        cmd = _make_cmd(caller, args)
        cmd.func()
        return _messages(caller)

    def test_evidence_requires_staff(self) -> None:
        non_staff = AccountFactory(is_staff=False)
        target = GMProfileFactory()
        caller = MagicMock()
        caller.msg = MagicMock()
        caller.account = non_staff

        messages = self._run(caller, f"evidence {target.account.username}")

        joined = " ".join(messages)
        self.assertIn("Only staff", joined)

    def test_evidence_requires_account_arg(self) -> None:
        staff_account = AccountFactory(is_staff=True)
        caller = MagicMock()
        caller.msg = MagicMock()
        caller.account = staff_account

        messages = self._run(caller, "evidence")

        joined = " ".join(messages)
        self.assertIn("Usage", joined)

    def test_evidence_target_without_profile_errors(self) -> None:
        staff_account = AccountFactory(is_staff=True)
        target = AccountFactory()
        caller = MagicMock()
        caller.msg = MagicMock()
        caller.account = staff_account

        messages = self._run(caller, f"evidence {target.username}")

        joined = " ".join(messages)
        self.assertIn("no GM profile", joined)

    def test_staff_evidence_renders_without_error(self) -> None:
        staff_account = AccountFactory(is_staff=True)
        target = GMProfileFactory(level=GMLevel.SENIOR)
        caller = MagicMock()
        caller.msg = MagicMock()
        caller.account = staff_account

        messages = self._run(caller, f"evidence {target.account.username}")

        joined = " ".join(messages)
        self.assertIn(target.account.username, joined)
        self.assertIn("Stories running", joined)


class CmdGMTrustPromoteTests(TestCase):
    def _run(self, caller, args: str) -> list[str]:
        cmd = _make_cmd(caller, args)
        cmd.func()
        return _messages(caller)

    def test_promote_requires_staff(self) -> None:
        non_staff = AccountFactory(is_staff=False)
        target = GMProfileFactory(level=GMLevel.STARTING)
        caller = MagicMock()
        caller.msg = MagicMock()
        caller.account = non_staff

        messages = self._run(caller, f"promote {target.account.username}=junior")

        joined = " ".join(messages)
        self.assertIn("Only staff", joined)
        target.refresh_from_db()
        self.assertEqual(target.level, GMLevel.STARTING)
        self.assertFalse(GMLevelChange.objects.filter(profile=target).exists())

    def test_staff_promote_end_to_end(self) -> None:
        staff_account = AccountFactory(is_staff=True)
        target = GMProfileFactory(level=GMLevel.STARTING)
        caller = MagicMock()
        caller.msg = MagicMock()
        caller.account = staff_account

        messages = self._run(
            caller, f"promote {target.account.username}=junior reason=strong first story"
        )

        target.refresh_from_db()
        self.assertEqual(target.level, GMLevel.JUNIOR)
        change = GMLevelChange.objects.get(profile=target)
        self.assertEqual(change.old_level, GMLevel.STARTING)
        self.assertEqual(change.new_level, GMLevel.JUNIOR)
        self.assertEqual(change.changed_by, staff_account)
        self.assertEqual(change.reason, "strong first story")
        joined = " ".join(messages)
        self.assertIn(target.account.username, joined)
        self.assertIn("Starting GM", joined)
        self.assertIn("Junior GM", joined)

    def test_promote_works_for_demotion(self) -> None:
        staff_account = AccountFactory(is_staff=True)
        target = GMProfileFactory(level=GMLevel.SENIOR)
        caller = MagicMock()
        caller.msg = MagicMock()
        caller.account = staff_account

        messages = self._run(
            caller, f"promote {target.account.username}=gm reason=needs closer supervision"
        )

        target.refresh_from_db()
        self.assertEqual(target.level, GMLevel.GM)
        joined = " ".join(messages)
        self.assertIn("Changed", joined)

    def test_promote_rejects_unknown_level(self) -> None:
        staff_account = AccountFactory(is_staff=True)
        target = GMProfileFactory(level=GMLevel.STARTING)
        caller = MagicMock()
        caller.msg = MagicMock()
        caller.account = staff_account

        messages = self._run(caller, f"promote {target.account.username}=nonsense")

        joined = " ".join(messages)
        self.assertIn("Unknown GM level", joined)
        target.refresh_from_db()
        self.assertEqual(target.level, GMLevel.STARTING)

    def test_promote_target_without_profile_errors(self) -> None:
        staff_account = AccountFactory(is_staff=True)
        target = AccountFactory()
        caller = MagicMock()
        caller.msg = MagicMock()
        caller.account = staff_account

        messages = self._run(caller, f"promote {target.username}=junior")

        joined = " ".join(messages)
        self.assertIn("no GM profile", joined)
