"""Tests for the ``covenant`` telnet command (#1346).

Exercises the namespaced subverb router end-to-end: engage/disengage/leave
run the real Actions and assert DB state; ambiguous-covenant and no-membership
error paths get focused coverage. The kick/rank/transfer/standdown paths are
covered by argument-parse and authority-check tests.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from django.test import TestCase

from commands.covenant import CmdCovenant
from world.covenants.constants import BattleBinding, CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantManagerRankFactory,
    CovenantRankFactory,
    CovenantRoleFactory,
)


def _run(caller: Any, args: str) -> CmdCovenant:
    """Build and execute a CmdCovenant wired to *caller* with *args*."""
    cmd = CmdCovenant()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"covenant {args}".strip()
    caller.msg = MagicMock()
    cmd.func()
    return cmd


def _capture(caller: Any) -> str:
    """Join all positional msg() args into one string."""
    return "\n".join(str(c.args[0]) for c in caller.msg.call_args_list if c.args)


class CmdCovenantEngageTests(TestCase):
    """Engage/disengage subverbs run the real Actions and mutate the DB.

    Uses a risen (non-dormant) BATTLE covenant so can_engage_membership passes.
    DURANCE covenants require a co-present scene and another active member;
    BATTLE only requires the covenant to be non-dormant.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.covenant = CovenantFactory(
            name="The Ashen Pact",
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
            is_dormant=False,
        )
        cls.role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        cls.membership = CharacterCovenantRoleFactory(
            covenant=cls.covenant,
            covenant_role=cls.role,
        )

    def test_engage_single_covenant(self) -> None:
        caller = self.membership.character_sheet.character
        _run(caller, "engage")
        self.membership.refresh_from_db()
        self.assertTrue(self.membership.engaged)
        caller.msg.assert_called()

    def test_engage_by_covenant_name(self) -> None:
        caller = self.membership.character_sheet.character
        _run(caller, "engage The Ashen Pact")
        self.membership.refresh_from_db()
        self.assertTrue(self.membership.engaged)

    def test_engage_sends_success_message(self) -> None:
        caller = self.membership.character_sheet.character
        _run(caller, "engage")
        text = _capture(caller)
        self.assertIn("engage", text.lower())

    def test_disengage_single_covenant(self) -> None:
        from world.covenants.services import set_engaged_membership

        set_engaged_membership(membership=self.membership)
        self.membership.refresh_from_db()
        self.assertTrue(self.membership.engaged)

        caller = self.membership.character_sheet.character
        _run(caller, "disengage")
        self.membership.refresh_from_db()
        self.assertFalse(self.membership.engaged)


class CmdCovenantLeaveTests(TestCase):
    """Leave subverb runs the real Action."""

    def test_leave_ends_membership(self) -> None:
        membership = CharacterCovenantRoleFactory()
        caller = membership.character_sheet.character
        _run(caller, "leave")
        membership.refresh_from_db()
        self.assertIsNotNone(membership.left_at)
        caller.msg.assert_called()


class CmdCovenantListTests(TestCase):
    """Bare ``covenant`` and ``covenant list`` render membership info."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.membership = CharacterCovenantRoleFactory(
            covenant=CovenantFactory(name="The Ashen Pact")
        )

    def test_bare_lists_membership(self) -> None:
        caller = self.membership.character_sheet.character
        _run(caller, "")
        text = _capture(caller)
        self.assertIn("The Ashen Pact", text)

    def test_list_subverb_lists_membership(self) -> None:
        caller = self.membership.character_sheet.character
        _run(caller, "list")
        text = _capture(caller)
        self.assertIn("The Ashen Pact", text)

    def test_no_memberships_shows_empty_message(self) -> None:
        # Use a fresh character with no covenant membership.
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        caller = sheet.character
        _run(caller, "")
        text = _capture(caller)
        self.assertIn("not a member", text.lower())


class CmdCovenantAmbiguousTests(TestCase):
    """Error paths: ambiguous covenant, unknown subverb, missing membership."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory

        cls.sheet = CharacterSheetFactory()
        # Use risen BATTLE covenants so test_engage_by_name_resolves_ambiguity passes
        # the can_engage_membership gate (DURANCE requires a co-present scene+member).
        cls.cov_a = CovenantFactory(
            name="First Covenant",
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
            is_dormant=False,
        )
        cls.cov_b = CovenantFactory(
            name="Second Covenant",
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
            is_dormant=False,
        )
        cls.role_a = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        cls.role_b = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        cls.mem_a = CharacterCovenantRoleFactory(
            character_sheet=cls.sheet, covenant=cls.cov_a, covenant_role=cls.role_a
        )
        cls.mem_b = CharacterCovenantRoleFactory(
            character_sheet=cls.sheet, covenant=cls.cov_b, covenant_role=cls.role_b
        )

    def test_engage_ambiguous_covenant_shows_error(self) -> None:
        caller = self.sheet.character
        _run(caller, "engage")
        text = _capture(caller)
        self.assertIn("First Covenant", text)
        self.assertIn("Second Covenant", text)

    def test_engage_by_name_resolves_ambiguity(self) -> None:
        caller = self.sheet.character
        _run(caller, "engage Second Covenant")
        self.mem_b.refresh_from_db()
        self.assertTrue(self.mem_b.engaged)

    def test_unknown_subverb_shows_usage(self) -> None:
        caller = self.sheet.character
        _run(caller, "frobnicate")
        text = _capture(caller)
        self.assertIn("Usage", text)

    def test_engage_nonexistent_covenant_name_shows_error(self) -> None:
        caller = self.sheet.character
        _run(caller, "engage Nonexistent Covenant")
        text = _capture(caller)
        self.assertIn("not a member", text.lower())


class CmdCovenantKickTests(TestCase):
    """Kick subverb checks authority and delegates to KickCovenantMemberAction."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory

        cls.covenant = CovenantFactory(name="Order of the Blade")
        cls.manager_rank = CovenantManagerRankFactory(covenant=cls.covenant)
        cls.plain_rank = CovenantRankFactory(covenant=cls.covenant, can_kick=False)
        # The actor has a manager rank (can kick).
        cls.actor_sheet = CharacterSheetFactory()
        cls.actor_membership = CharacterCovenantRoleFactory(
            character_sheet=cls.actor_sheet,
            covenant=cls.covenant,
            rank=cls.manager_rank,
        )
        # The target is a plain member.
        cls.target_sheet = CharacterSheetFactory()
        cls.target_membership = CharacterCovenantRoleFactory(
            character_sheet=cls.target_sheet,
            covenant=cls.covenant,
            rank=cls.plain_rank,
        )

    def test_kick_without_authority_shows_error(self) -> None:
        # A character with no can_kick rank cannot kick.
        caller = self.target_sheet.character
        caller.msg = MagicMock()
        caller.search = MagicMock(return_value=self.actor_sheet.character)
        cmd = CmdCovenant()
        cmd.caller = caller
        cmd.args = f"kick {self.actor_sheet.character.db_key}"
        cmd.raw_string = cmd.args
        cmd.func()
        text = "\n".join(str(c.args[0]) for c in caller.msg.call_args_list if c.args)
        self.assertIn("authority", text.lower())

    def test_kick_missing_target_shows_usage(self) -> None:
        caller = self.actor_sheet.character
        caller.msg = MagicMock()
        caller.search = MagicMock(return_value=None)
        cmd = CmdCovenant()
        cmd.caller = caller
        cmd.args = "kick"
        cmd.raw_string = "covenant kick"
        cmd.func()
        text = "\n".join(str(c.args[0]) for c in caller.msg.call_args_list if c.args)
        self.assertIn("whom", text.lower())


class CmdCovenantRankTests(TestCase):
    """Rank subverb argument parsing and authority checks."""

    def test_rank_too_few_args_shows_usage(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory

        covenant = CovenantFactory(name="Iron Vow")
        manager_rank = CovenantManagerRankFactory(covenant=covenant)
        sheet = CharacterSheetFactory()
        CharacterCovenantRoleFactory(character_sheet=sheet, covenant=covenant, rank=manager_rank)
        caller = sheet.character
        caller.msg = MagicMock()
        caller.search = MagicMock(return_value=None)
        cmd = CmdCovenant()
        cmd.caller = caller
        cmd.args = "rank"
        cmd.raw_string = "covenant rank"
        cmd.func()
        text = "\n".join(str(c.args[0]) for c in caller.msg.call_args_list if c.args)
        self.assertIn("Usage", text)
