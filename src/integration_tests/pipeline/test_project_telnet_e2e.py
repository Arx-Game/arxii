"""Telnet E2E: project contribution journey (#1574).

Drives ``CmdProject`` end-to-end through the three contribution paths
(donate / check / story) + the status display, asserting DB state after each
step and telnet feedback via ``caller.msg``.

Journey layout:
  1. ``+project <id>``           — status display (progress, threshold, coin cost).
  2. ``project/donate <id>=<n>`` — money path: debits the purse, advances progress 1 per 100c.
  3. ``project/check <id>=<m>``  — check path: spends AP, rolls (patched), advances on success.
  4. ``project/story <id>=<t>`` — records narrative on the latest contribution.

All assertions run on the SQLite fast tier — no ``@tag("postgres")`` needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.utils import idmapper

from commands.projects import CmdProject
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse
from world.projects.constants import (
    CompletionMode,
    ContributionKind,
    ProjectKind,
    ProjectStatus,
)
from world.projects.factories import ProjectFactory
from world.projects.models import Contribution, ContributionMethod
from world.projects.services import add_contribution

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pc(name: str, room: object) -> tuple[object, object]:
    """Create a PC character + sheet in *room*. Returns (character, sheet)."""
    char = CharacterFactory(db_key=name, location=room)
    sheet = CharacterSheetFactory(character=char)
    return char, sheet


def _run(caller: object, args: str = "", switches: list[str] | None = None) -> CmdProject:
    """Wire CmdProject to *caller* and call func(). Returns the cmd instance."""
    cmd = CmdProject()
    cmd.caller = caller
    cmd.args = args
    cmd.switches = switches or []
    cmd.raw_string = "project " + (" ".join(f"/{s}" for s in (switches or []))) + f" {args}"
    cmd.cmdname = "project"
    caller.msg = MagicMock()
    cmd.func()
    return cmd


# ---------------------------------------------------------------------------
# Journey
# ---------------------------------------------------------------------------


class ProjectContributionE2EJourneyTest(TestCase):
    """Donate → status → check → story through telnet CmdProject."""

    def setUp(self) -> None:
        idmapper.models.flush_cache()
        self.room = ObjectDBFactory(
            db_key="ProjectE2ERoom", db_typeclass_path="typeclasses.rooms.Room"
        )

        self.donor_char, self.donor_sheet = _make_pc("Donor", self.room)
        self.donor_persona = self.donor_sheet.primary_persona

        # Give the donor a purse with 500 coppers.
        self.purse = get_or_create_purse(self.donor_sheet)
        self.purse.balance = 500
        self.purse.save(update_fields=["balance"])

        # An ACTIVE money-threshold project (1 progress per 100 coppers donated).
        self.project = ProjectFactory(
            kind=ProjectKind.TEST_KIND,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            status=ProjectStatus.ACTIVE,
            threshold_target=5,
            current_progress=0,
            description="Build the bridge",
        )

    # ------------------------------------------------------------------
    # status display
    # ------------------------------------------------------------------

    def test_status_shows_progress_and_remaining_coin(self) -> None:
        """+project <id> → progress, threshold, and remaining-to-fund display."""
        _run(self.donor_char, str(self.project.pk))

        msg = self.donor_char.msg.call_args[0][0]
        self.assertIn(f"#{self.project.pk}", msg, "status should show the project id")
        self.assertIn("Build the bridge", msg, "status should show the description")
        self.assertIn("0/5", msg, "status should show current progress / target")
        self.assertIn("5g", msg, "status should show remaining coin to fund (5 gold = 500c)")

    # ------------------------------------------------------------------
    # donate (money path)
    # ------------------------------------------------------------------

    def test_donate_debits_purse_and_advances_progress(self) -> None:
        """project/donate <id>=<amount> → purse debited, progress advanced."""
        _run(self.donor_char, f"{self.project.pk}=200", switches=["donate"])

        # Purse: 500 - 200 = 300 coppers remaining.
        self.purse.refresh_from_db()
        self.assertEqual(self.purse.balance, 300, "donate should debit the purse by 200")

        # Progress: 200 coppers = 2 progress (1 per 100c).
        self.project.refresh_from_db()
        self.assertEqual(self.project.current_progress, 2, "200c should advance progress by 2")

        # A MONEY contribution was recorded.
        contribution = Contribution.objects.filter(
            project=self.project,
            contributor_persona=self.donor_persona,
            kind=ContributionKind.MONEY,
        ).first()
        self.assertIsNotNone(contribution, "a MONEY contribution should be recorded")
        self.assertEqual(contribution.money_amount, 200)

        self.donor_char.msg.assert_called()
        donate_msg = self.donor_char.msg.call_args[0][0]
        self.assertIn("donate", donate_msg.lower())

    def test_donate_insufficient_funds_fails_gracefully(self) -> None:
        """project/donate with more than the purse balance → failure message, no progress."""
        _run(self.donor_char, f"{self.project.pk}=1000", switches=["donate"])

        self.purse.refresh_from_db()
        self.assertEqual(self.purse.balance, 500, "failed donate should not debit the purse")

        self.project.refresh_from_db()
        self.assertEqual(
            self.project.current_progress, 0, "failed donate should not advance progress"
        )

        self.donor_char.msg.assert_called()
        self.assertIn("insufficient", self.donor_char.msg.call_args[0][0].lower())

    # ------------------------------------------------------------------
    # check (check-based contribution)
    # ------------------------------------------------------------------

    def test_check_spends_ap_and_advances_on_success(self) -> None:
        """project/check <id>=<method> → AP spent, check rolled, progress advanced on success."""
        # Need a ContributionMethod for the project's kind + a CheckType.
        from world.checks.factories import CheckTypeFactory

        check_type = CheckTypeFactory()
        ContributionMethod.objects.create(
            kind=ProjectKind.TEST_KIND,
            name="Inspect",
            check_type=check_type,
            ap_cost=1,
            progress_on_success=3,
            is_active=True,
        )

        # Give the donor AP.
        from world.action_points.models import ActionPointPool

        pool = ActionPointPool.get_or_create_for_character(self.donor_char)
        pool.current = 5
        pool.save(update_fields=["current"])

        # Patch perform_check to return a successful result.
        # result.outcome must be a *saved* CheckOutcome (it's FK-stored on Contribution).
        from world.traits.factories import CheckOutcomeFactory

        mock_result = MagicMock()
        mock_result.outcome = CheckOutcomeFactory(success_level=2, name="Good")
        mock_result.success_level = 2

        with patch("world.checks.services.perform_check", return_value=mock_result):
            _run(self.donor_char, f"{self.project.pk}=Inspect", switches=["check"])

        # AP spent.
        pool.refresh_from_db()
        self.assertEqual(pool.current, 4, "check should spend 1 AP")

        # Progress advanced by method.progress_on_success (3).
        self.project.refresh_from_db()
        self.assertEqual(self.project.current_progress, 3, "successful check should advance by 3")

        # A CHECK contribution was recorded.
        contribution = Contribution.objects.filter(
            project=self.project,
            contributor_persona=self.donor_persona,
            kind=ContributionKind.CHECK,
        ).first()
        self.assertIsNotNone(contribution, "a CHECK contribution should be recorded")

        self.donor_char.msg.assert_called()
        check_msg = self.donor_char.msg.call_args[0][0]
        self.assertIn("advances", check_msg.lower())

    # ------------------------------------------------------------------
    # story (narrative recording)
    # ------------------------------------------------------------------

    def test_story_records_narrative_on_latest_contribution(self) -> None:
        """project/story <id>=<text> → narrative recorded on latest contribution."""
        # First, make a contribution so there's something to attach the story to.
        add_contribution(
            project=self.project,
            contributor_persona=self.donor_persona,
            kind=ContributionKind.MONEY,
            money_amount=100,
        )

        story_text = "I hauled timber all day"
        _run(self.donor_char, f"{self.project.pk}={story_text}", switches=["story"])

        contribution = (
            Contribution.objects.filter(
                project=self.project,
                contributor_persona=self.donor_persona,
            )
            .order_by("-occurred_at")
            .first()
        )
        self.assertIsNotNone(contribution, "should have a contribution to attach the story to")
        self.assertEqual(
            contribution.intent_text, story_text, "story should be recorded on the contribution"
        )

        self.donor_char.msg.assert_called()
        story_msg = self.donor_char.msg.call_args[0][0]
        self.assertIn("recorded", story_msg.lower())

    def test_story_without_prior_contribution_fails(self) -> None:
        """project/story with no prior contribution → failure message."""
        _run(self.donor_char, f"{self.project.pk}=My tale", switches=["story"])

        self.donor_char.msg.assert_called()
        msg = self.donor_char.msg.call_args[0][0]
        self.assertIn("not contributed", msg.lower())
