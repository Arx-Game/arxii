"""Telnet E2E: covenant membership lifecycle journey (#1346).

Drives the full engagement, rank-assignment, stand-down, banner-call rise, and
induction journeys through CmdCovenant and CmdRitual, asserting DB state after
each step and (where natural) command feedback.

Journey layout:
  - ``CovenantMembershipRankStanddownTests``:
      engage → rank-assign → stand-down via ``CmdCovenant``.
  - ``BannerCallRiseTests``:
      ritual draft/join/fire rises a dormant STANDING battle covenant.
  - ``CovenantInductionTests``:
      ritual draft/join/fire inducts an outsider into a covenant.

All three test classes run on the SQLite fast tier; no ``@tag("postgres")`` was
required — none of the service paths hit PG-only constructs (DISTINCT ON,
materialised views) on the journeys exercised here.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.covenant import CmdCovenant
from commands.ritual import CmdRitual
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import BattleBinding, CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantManagerRankFactory,
    CovenantRankFactory,
    CovenantRoleFactory,
)
from world.covenants.models import CharacterCovenantRole
from world.magic.factories import BattleCovenantRiseRitualFactory, CovenantInductionRitualFactory
from world.magic.models.sessions import RitualSession


def _run(cmd_cls: type, caller: object, args: str = "") -> object:
    """Helper: build a command instance wired to *caller* (mirrors ritual-session E2E).

    Sets ``caller.msg`` to a fresh ``MagicMock`` so each invocation starts with
    a clean message capture. Does **not** call ``func()`` — the caller site does
    that after any additional wiring (e.g. ``cmd.caller.search``).
    """
    cmd = cmd_cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd_cls.key} {args}".strip()
    caller.msg = MagicMock()
    return cmd


# ---------------------------------------------------------------------------
# Journey 1 — membership engage, rank assignment, stand-down
# ---------------------------------------------------------------------------


class CovenantMembershipRankStanddownTests(TestCase):
    """engage → rank-assign → standdown via CmdCovenant against a BATTLE STANDING covenant."""

    def setUp(self) -> None:
        # setUp (not setUpTestData) avoids the DbHolder deepcopy flake in CI shards.
        self.covenant = CovenantFactory(
            name="Iron Banner",
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
            is_dormant=False,
        )
        self.role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)

        # Two ranks for the covenant: a manager rank (officer) and a plain rank (member).
        self.manager_rank = CovenantManagerRankFactory(covenant=self.covenant, name="Commander")
        self.plain_rank = CovenantRankFactory(
            covenant=self.covenant, name="Soldier", can_manage_ranks=False
        )
        # A third rank to promote the member to.
        self.veteran_rank = CovenantRankFactory(
            covenant=self.covenant, name="Veteran", can_manage_ranks=False
        )

        self.officer_sheet = CharacterSheetFactory()
        self.member_sheet = CharacterSheetFactory()

        self.officer_membership = CharacterCovenantRoleFactory(
            character_sheet=self.officer_sheet,
            covenant=self.covenant,
            covenant_role=self.role,
            rank=self.manager_rank,
        )
        self.member_membership = CharacterCovenantRoleFactory(
            character_sheet=self.member_sheet,
            covenant=self.covenant,
            covenant_role=self.role,
            rank=self.plain_rank,
        )

    def test_engage(self) -> None:
        """covenant engage → officer membership becomes engaged=True."""
        officer = self.officer_sheet.character
        cmd = _run(CmdCovenant, officer, "engage")
        cmd.func()

        self.officer_membership.refresh_from_db()
        self.assertTrue(self.officer_membership.engaged)
        officer.msg.assert_called()
        self.assertIn("engage", officer.msg.call_args[0][0].lower())

    def test_rank_assignment(self) -> None:
        """covenant rank <member> Veteran → member's rank updated to veteran_rank."""
        officer = self.officer_sheet.character
        member = self.member_sheet.character
        member_key = member.db_key

        cmd = _run(CmdCovenant, officer, f"rank {member_key} Veteran")
        cmd.caller.search = MagicMock(return_value=member)
        cmd.func()

        self.member_membership.refresh_from_db()
        self.assertEqual(self.member_membership.rank, self.veteran_rank)
        officer.msg.assert_called()

    def test_standdown(self) -> None:
        """covenant standdown → BATTLE STANDING covenant becomes dormant."""
        officer = self.officer_sheet.character
        cmd = _run(CmdCovenant, officer, "standdown")
        cmd.func()

        self.covenant.refresh_from_db()
        self.assertTrue(self.covenant.is_dormant)
        officer.msg.assert_called()
        self.assertIn("stand", officer.msg.call_args[0][0].lower())


# ---------------------------------------------------------------------------
# Journey 2 — banner-call rise
# ---------------------------------------------------------------------------


class BannerCallRiseTests(TestCase):
    """ritual draft → join → fire rises a dormant STANDING battle covenant."""

    def setUp(self) -> None:
        self.ritual = BattleCovenantRiseRitualFactory()
        self.covenant = CovenantFactory(
            name="Steel Oath",
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
            is_dormant=True,
        )
        self.role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        self.plain_rank = CovenantRankFactory(covenant=self.covenant, name="Blade")

        self.initiator_sheet = CharacterSheetFactory()
        self.member_sheet = CharacterSheetFactory()

        # Both hold active memberships in the dormant covenant.
        self.initiator_membership = CharacterCovenantRoleFactory(
            character_sheet=self.initiator_sheet,
            covenant=self.covenant,
            covenant_role=self.role,
            rank=self.plain_rank,
        )
        self.member_membership = CharacterCovenantRoleFactory(
            character_sheet=self.member_sheet,
            covenant=self.covenant,
            covenant_role=self.role,
            rank=self.plain_rank,
        )

    def test_banner_call_rise_journey(self) -> None:
        """draft → join → fire flips is_dormant→False and engages both participants."""
        initiator = self.initiator_sheet.character
        member = self.member_sheet.character

        # 1. Initiator drafts the rise session.
        cmd = _run(
            CmdRitual,
            initiator,
            f"draft Call the Banners invite={member.db_key} covenant=Steel Oath",
        )
        cmd.caller.search = MagicMock(return_value=member)
        cmd.func()

        session = RitualSession.objects.get(ritual=self.ritual)
        session_pk = session.pk
        initiator.msg.assert_called()
        self.assertIn(str(session_pk), initiator.msg.call_args[0][0])

        # 2. Member joins the session.
        cmd = _run(CmdRitual, member, f"join {session_pk}")
        cmd.func()
        member.msg.assert_called()
        self.assertIn("joined", member.msg.call_args[0][0])

        # 3. Initiator fires — covenant rises.
        cmd = _run(CmdRitual, initiator, f"fire {session_pk}")
        cmd.func()
        initiator.msg.assert_called()
        self.assertIn("complete", initiator.msg.call_args[0][0])

        # Session consumed.
        self.assertFalse(RitualSession.objects.filter(pk=session_pk).exists())

        # Covenant is no longer dormant.
        self.covenant.refresh_from_db()
        self.assertFalse(self.covenant.is_dormant)

        # Both participants are now engaged.
        self.initiator_membership.refresh_from_db()
        self.member_membership.refresh_from_db()
        self.assertTrue(self.initiator_membership.engaged)
        self.assertTrue(self.member_membership.engaged)


# ---------------------------------------------------------------------------
# Journey 3 — covenant induction
# ---------------------------------------------------------------------------


class CovenantInductionTests(TestCase):
    """ritual draft → join (role=…) → fire inducts an outsider into a covenant."""

    def setUp(self) -> None:
        self.ritual = CovenantInductionRitualFactory()
        self.covenant = CovenantFactory(name="Silver Circle", covenant_type=CovenantType.DURANCE)

        # Initiator holds a can_invite rank in the covenant.
        self.invite_rank = CovenantManagerRankFactory(
            covenant=self.covenant, name="Elder", can_invite=True
        )
        # Outsider role — looked up by name in CovenantInductionAdapter.parse_join.
        self.outsider_role = CovenantRoleFactory(name="Warden", covenant_type=CovenantType.DURANCE)

        self.initiator_sheet = CharacterSheetFactory()
        self.outsider_sheet = CharacterSheetFactory()

        self.initiator_membership = CharacterCovenantRoleFactory(
            character_sheet=self.initiator_sheet,
            covenant=self.covenant,
            covenant_role=CovenantRoleFactory(covenant_type=CovenantType.DURANCE),
            rank=self.invite_rank,
        )

    def test_induction_journey(self) -> None:
        """draft → join role=Warden → fire creates an active membership for the outsider."""
        initiator = self.initiator_sheet.character
        outsider = self.outsider_sheet.character

        # 1. Initiator drafts the induction session.
        cmd = _run(
            CmdRitual,
            initiator,
            f"draft Covenant Induction invite={outsider.db_key} covenant=Silver Circle",
        )
        cmd.caller.search = MagicMock(return_value=outsider)
        cmd.func()

        session = RitualSession.objects.get(ritual=self.ritual)
        session_pk = session.pk
        initiator.msg.assert_called()
        self.assertIn(str(session_pk), initiator.msg.call_args[0][0])

        # 2. Outsider joins, declaring their role.
        cmd = _run(CmdRitual, outsider, f"join {session_pk} role=Warden")
        cmd.func()
        outsider.msg.assert_called()
        self.assertIn("joined", outsider.msg.call_args[0][0])

        # 3. Initiator fires — outsider inducted.
        cmd = _run(CmdRitual, initiator, f"fire {session_pk}")
        cmd.func()
        initiator.msg.assert_called()
        self.assertIn("complete", initiator.msg.call_args[0][0])

        # Session consumed.
        self.assertFalse(RitualSession.objects.filter(pk=session_pk).exists())

        # Outsider now has an active CharacterCovenantRole in Silver Circle with the Warden role.
        new_membership = CharacterCovenantRole.objects.filter(
            character_sheet=self.outsider_sheet,
            covenant=self.covenant,
            left_at__isnull=True,
        ).first()
        self.assertIsNotNone(new_membership)
        self.assertEqual(new_membership.covenant_role, self.outsider_role)
