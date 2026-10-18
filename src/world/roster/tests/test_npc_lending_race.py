"""The accept race (#4418): a competing ACTIVE loan the lock could not see is a refusal."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from world.roster.constants import NPCLoanStatus
from world.roster.factories import NPCLoanFactory, RosterEntryFactory
from world.roster.models import NPCLoan
from world.roster.services.npc_lending import JUST_LENT_MESSAGE, NPCLendingError, _activate


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
