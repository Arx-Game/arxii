"""Schema tests for lending a major NPC (#4418)."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.roster.constants import NPCLoanStatus
from world.roster.factories import NPCLoanFactory, RosterEntryFactory


class NPCLoanConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.entry = RosterEntryFactory()

    def test_one_active_loan_per_entry(self) -> None:
        NPCLoanFactory(roster_entry=self.entry, status=NPCLoanStatus.ACTIVE)
        with self.assertRaises(IntegrityError), transaction.atomic():
            NPCLoanFactory(roster_entry=self.entry, status=NPCLoanStatus.ACTIVE)

    def test_offered_loans_may_coexist(self) -> None:
        NPCLoanFactory(roster_entry=self.entry, status=NPCLoanStatus.OFFERED)
        NPCLoanFactory(roster_entry=self.entry, status=NPCLoanStatus.OFFERED)
        NPCLoanFactory(roster_entry=self.entry, status=NPCLoanStatus.ACTIVE)
        self.assertEqual(self.entry.npc_loans.count(), 3)
