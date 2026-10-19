"""The accept race (#4418): a competing ACTIVE loan the lock could not see is a refusal."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from django.test import TestCase

from world.roster.constants import NPCLoanStatus
from world.roster.factories import NPCLoanFactory, RosterEntryFactory
from world.roster.models import NPCLoan
from world.roster.services.npc_lending import (
    JUST_LENT_MESSAGE,
    NPCLendingError,
    _activate,
    answer_loan,
    end_loan,
)


def _change_behind_the_cache(loan: NPCLoan, **fields: object) -> None:
    """Write ``loan``'s row without touching the cached instance, as a racing
    request in another process would."""
    NPCLoan.objects.filter(pk=loan.pk).update_with_reason(
        reason="test: a competing write the cached instance has not seen", **fields
    )


class DecidingOnTheDatabaseStatusTests(TestCase):
    def test_an_answer_sees_a_decline_that_landed_first(self) -> None:
        loan = NPCLoanFactory(status=NPCLoanStatus.OFFERED)
        _change_behind_the_cache(loan, status=NPCLoanStatus.DECLINED)
        self.assertEqual(loan.status, NPCLoanStatus.OFFERED)

        with self.assertRaises(NPCLendingError) as refused:
            answer_loan(loan=loan, accept=False, by=loan.borrower)

        self.assertEqual(refused.exception.user_message, "That loan has already been answered.")
        self.assertEqual(loan.status, NPCLoanStatus.DECLINED)

    def test_a_take_back_sees_an_end_that_landed_first(self) -> None:
        loan = NPCLoanFactory(status=NPCLoanStatus.ACTIVE)
        ended_first = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
        _change_behind_the_cache(loan, status=NPCLoanStatus.ENDED, ended_at=ended_first)
        self.assertEqual(loan.status, NPCLoanStatus.ACTIVE)

        end_loan(loan, by=None)

        self.assertEqual(loan.status, NPCLoanStatus.ENDED)
        self.assertEqual(loan.ended_at, ended_first)
        self.assertEqual(
            NPCLoan.objects.filter(pk=loan.pk).values_list("ended_at", flat=True).get(),
            ended_first,
        )


class ActivatingOverACompetingLoanTests(TestCase):
    def test_a_competing_active_loan_turns_the_accept_into_a_refusal(self) -> None:
        entry = RosterEntryFactory()
        already = NPCLoanFactory(roster_entry=entry, status=NPCLoanStatus.ACTIVE)
        waiting = NPCLoanFactory(roster_entry=entry, status=NPCLoanStatus.OFFERED)

        # The competing ACTIVE row lands after the lock: nothing ends it first.
        with (
            patch("world.roster.services.npc_lending.end_loan"),
            self.assertRaises(NPCLendingError) as refused,
        ):
            _activate(waiting)

        self.assertEqual(refused.exception.user_message, JUST_LENT_MESSAGE)
        NPCLoan.flush_instance_cache()
        self.assertEqual(NPCLoan.objects.get(pk=waiting.pk).status, NPCLoanStatus.OFFERED)
        self.assertEqual(NPCLoan.objects.get(pk=already.pk).status, NPCLoanStatus.ACTIVE)
