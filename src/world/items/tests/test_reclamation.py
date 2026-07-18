"""Theft reclamation tests (#2368) — claims, the trace, both routes, standing."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import ClaimStatus, OwnershipEventType
from world.items.factories import ItemInstanceFactory
from world.items.models import OwnershipEvent
from world.items.services.provenance import has_unresolved_stolen_provenance
from world.items.services.reclamation import (
    ReclamationError,
    advance_trace,
    assign_claim,
    execute_lawful_seizure,
    file_reclamation_accusation,
    file_theft_claim,
    has_reclamation_standing,
    record_steal_back,
    trace_complete,
)


class ReclamationFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.victim = CharacterSheetFactory()
        cls.fence = CharacterSheetFactory()
        cls.holder = CharacterSheetFactory()
        cls.item = ItemInstanceFactory(holder_character_sheet=cls.holder)
        # The real chain: stolen from victim → fenced → sold to holder.
        OwnershipEvent.objects.create(
            item_instance=cls.item,
            event_type=OwnershipEventType.STOLEN,
            from_character_sheet=cls.victim,
            to_character_sheet=cls.fence,
        )
        OwnershipEvent.objects.create(
            item_instance=cls.item,
            event_type=OwnershipEventType.TRANSFERRED,
            from_character_sheet=cls.fence,
            to_character_sheet=cls.holder,
        )

    def _traced_claim(self):
        claim = file_theft_claim(self.victim, self.item)
        while not trace_complete(claim):
            advance_trace(claim, check_level=2)
            claim.refresh_from_db()
        return claim


class ClaimTests(ReclamationFixture):
    def test_only_the_provenance_victim_files(self):
        with self.assertRaises(ReclamationError):
            file_theft_claim(self.fence, self.item)
        claim = file_theft_claim(self.victim, self.item)
        self.assertEqual(claim.original_claimant_sheet, self.victim)

    def test_duplicate_open_claim_rejected(self):
        file_theft_claim(self.victim, self.item)
        with self.assertRaises(ReclamationError):
            file_theft_claim(self.victim, self.item)


class TraceTests(ReclamationFixture):
    def test_hops_reveal_one_at_a_time_then_holder(self):
        claim = file_theft_claim(self.victim, self.item)
        out1 = advance_trace(claim, check_level=1)
        claim.refresh_from_db()
        self.assertFalse(out1["complete"])
        self.assertEqual(claim.trace_steps.count(), 1)
        out2 = advance_trace(claim, check_level=1)
        claim.refresh_from_db()
        self.assertTrue(out2["complete"])
        self.assertTrue(out2["holder_revealed"])
        self.assertEqual(claim.trace_steps.count(), 2)

    def test_failure_reveals_nothing_and_botch_chills(self):
        claim = file_theft_claim(self.victim, self.item)
        advance_trace(claim, check_level=-1)
        claim.refresh_from_db()
        self.assertEqual(claim.trace_steps.count(), 0)
        out = advance_trace(claim, check_level=-3)
        self.assertTrue(out["chilled"])
        claim.refresh_from_db()
        with self.assertRaises(ReclamationError):
            advance_trace(claim, check_level=2)


class AssignmentTests(ReclamationFixture):
    def test_assignment_moves_trace_but_never_the_immunity(self):
        claim = file_theft_claim(self.victim, self.item)
        advance_trace(claim, check_level=1)
        claim.refresh_from_db()
        hunter = CharacterSheetFactory()
        new_claim = assign_claim(claim, hunter)
        claim.refresh_from_db()
        self.assertEqual(claim.status, ClaimStatus.RELEASED)
        self.assertEqual(new_claim.claimant_sheet, hunter)
        self.assertEqual(new_claim.original_claimant_sheet, self.victim)
        self.assertEqual(new_claim.trace_position, 1)
        self.assertEqual(new_claim.trace_steps.count(), 1)
        # Standing stays with the wronged, not the document.
        self.assertFalse(has_reclamation_standing(hunter, self.item))
        self.assertTrue(has_reclamation_standing(self.victim, self.item))


class RouteTests(ReclamationFixture):
    def test_routes_require_a_completed_trace(self):
        claim = file_theft_claim(self.victim, self.item)
        with self.assertRaises(ReclamationError):
            execute_lawful_seizure(claim)
        with self.assertRaises(ReclamationError):
            record_steal_back(claim, self.victim)
        with self.assertRaises(ReclamationError):
            file_reclamation_accusation(claim)

    def test_lawful_seizure_returns_item_and_clears_provenance(self):
        claim = self._traced_claim()
        self.assertTrue(has_unresolved_stolen_provenance(self.item))
        execute_lawful_seizure(claim)
        self.item.refresh_from_db()
        claim.refresh_from_db()
        self.assertEqual(self.item.holder_character_sheet, self.victim)
        self.assertEqual(claim.status, ClaimStatus.RECOVERED_LAWFUL)
        self.assertTrue(
            OwnershipEvent.objects.filter(
                item_instance=self.item, event_type=OwnershipEventType.RECOVERED
            ).exists()
        )
        self.assertFalse(has_unresolved_stolen_provenance(self.item))

    def test_steal_back_standing_enforced(self):
        claim = self._traced_claim()
        stranger = CharacterSheetFactory()
        with self.assertRaises(ReclamationError):
            record_steal_back(claim, stranger)
        record_steal_back(claim, self.victim)
        self.item.refresh_from_db()
        claim.refresh_from_db()
        self.assertEqual(self.item.holder_character_sheet, self.victim)
        self.assertEqual(claim.status, ClaimStatus.RECOVERED_TAKEN)

    def test_accusation_degrades_gracefully_without_located_holder(self):
        claim = self._traced_claim()
        # Factory characters have no location: no jurisdiction, no heat, no error.
        self.assertFalse(file_reclamation_accusation(claim))
