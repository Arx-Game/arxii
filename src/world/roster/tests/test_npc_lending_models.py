"""Schema tests for lending a major NPC (#4418)."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.roster.constants import NPCLoanStatus
from world.roster.factories import (
    NPCLoanFactory,
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.roster.models import RosterEntry
from world.roster.services.npc_lending import playable_entries


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


class PlayableByMatchesPlayableEntries(TestCase):
    """``RosterEntry.objects.playable_by`` (one query, ``Account.cached_roster_entries``)
    gives the same entries as ``playable_entries`` over the loans in hand."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.holder = PlayerDataFactory().account
        cls.borrower = PlayerDataFactory().account
        cls.bystander = PlayerDataFactory().account
        cls.lent = cls._held_by(cls.holder)
        cls.kept = cls._held_by(cls.holder)
        cls.returned = cls._held_by(cls.holder)
        cls.own = cls._held_by(cls.borrower)
        cls.watched = cls._held_by(cls.bystander)
        NPCLoanFactory(roster_entry=cls.lent, borrower=cls.borrower, status=NPCLoanStatus.ACTIVE)
        NPCLoanFactory(roster_entry=cls.kept, borrower=cls.borrower, status=NPCLoanStatus.OFFERED)
        NPCLoanFactory(roster_entry=cls.kept, borrower=cls.bystander, status=NPCLoanStatus.OFFERED)
        NPCLoanFactory(roster_entry=cls.returned, borrower=cls.borrower, status=NPCLoanStatus.ENDED)

    @staticmethod
    def _held_by(account) -> RosterEntry:
        entry = RosterEntryFactory()
        RosterTenureFactory(roster_entry=entry, player_data=account.player_data, end_date=None)
        return entry

    def _both(self, account) -> tuple[set[int], set[int]]:
        in_memory = playable_entries(account, list(RosterEntry.objects.for_account(account)))
        one_query = RosterEntry.objects.playable_by(account)
        return {entry.pk for entry in in_memory}, {entry.pk for entry in one_query}

    def test_the_holder_loses_only_the_npc_lent_away(self) -> None:
        in_memory, one_query = self._both(self.holder)
        self.assertEqual(one_query, {self.kept.pk, self.returned.pk})
        self.assertEqual(one_query, in_memory)

    def test_the_borrower_plays_their_own_and_the_active_loan(self) -> None:
        in_memory, one_query = self._both(self.borrower)
        self.assertEqual(one_query, {self.own.pk, self.lent.pk})
        self.assertEqual(one_query, in_memory)

    def test_a_bystander_with_only_an_offer_keeps_their_own(self) -> None:
        in_memory, one_query = self._both(self.bystander)
        self.assertEqual(one_query, {self.watched.pk})
        self.assertEqual(one_query, in_memory)

    def test_it_is_one_query(self) -> None:
        with self.assertNumQueries(1):
            list(RosterEntry.objects.playable_by(self.borrower))
