"""CLUE_REVEAL offer kind (#3428) — NPC-held clues.

Covers the spec's service seam journey: eligibility gating (offer listed only
while unheld), check-gated resolve (success grants via grant_clue_target,
failure grants nothing and leaves the clue unheld), the no-check
auto-success path, the already-holding exclusion after a successful reveal,
and the roster-tenure fail-closed case.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.clues.factories import CharacterClueFactory, ClueFactory
from world.clues.models import CharacterClue
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CodexEntryFactory
from world.codex.models import CharacterCodexKnowledge
from world.npc_services.constants import OfferKind
from world.npc_services.effects import dispatch_offer_effect, run_clue_reveal_offer
from world.npc_services.factories import (
    ClueRevealOfferDetailsFactory,
    NPCRoleFactory,
    NPCServiceOfferFactory,
)
from world.npc_services.services import (
    available_offers,
    resolve_offer,
    start_interaction,
)
from world.roster.factories import RosterEntryFactory


def _pc_with_roster_entry():
    """A PC with sheet + PRIMARY persona + a RosterEntry sharing that sheet."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    roster_entry = RosterEntryFactory(character_sheet=sheet)
    return character, sheet.primary_persona, roster_entry


class ClueRevealListingEligibilityTests(TestCase):
    """`available_offers` excludes CLUE_REVEAL offers whose clue is already held."""

    def setUp(self) -> None:
        self.character, self.persona, self.roster_entry = _pc_with_roster_entry()
        self.role = NPCRoleFactory(name="Threshold Warden")
        self.entry = CodexEntryFactory()
        self.clue = ClueFactory(target_codex_entry=self.entry, name="Where the Smugglers Land")
        self.offer = NPCServiceOfferFactory(
            role=self.role,
            kind=OfferKind.CLUE_REVEAL,
            label="Ask about the smugglers",
            is_final=True,
        )
        ClueRevealOfferDetailsFactory(offer=self.offer, clue=self.clue)

    def test_offer_listed_when_clue_unheld(self) -> None:
        session = start_interaction(role=self.role, persona=self.persona, character=self.character)
        offers = available_offers(session)
        self.assertIn(self.offer, offers)

    def test_offer_excluded_once_clue_already_held(self) -> None:
        CharacterClueFactory(roster_entry=self.roster_entry, clue=self.clue)
        session = start_interaction(role=self.role, persona=self.persona, character=self.character)
        offers = available_offers(session)
        self.assertNotIn(self.offer, offers)

    def test_ineligible_rapport_gate_never_shown(self) -> None:
        # A rapport floor above the interaction's starting rapport hides the offer —
        # the same generic gate every offer kind shares (#686), exercised here for
        # CLUE_REVEAL specifically (spec: "ineligible player never sees it").
        self.offer.rapport_requirement = 1000
        self.offer.save()
        session = start_interaction(role=self.role, persona=self.persona, character=self.character)
        offers = available_offers(session)
        self.assertNotIn(self.offer, offers)

    def test_missing_details_row_fails_closed(self) -> None:
        bare_offer = NPCServiceOfferFactory(
            role=self.role, kind=OfferKind.CLUE_REVEAL, label="No details row", is_final=True
        )
        session = start_interaction(role=self.role, persona=self.persona, character=self.character)
        offers = available_offers(session)
        self.assertNotIn(bare_offer, offers)

    def test_persona_with_no_roster_entry_fails_closed(self) -> None:
        character = CharacterFactory()
        sheet = CharacterSheetFactory(character=character)
        persona = sheet.primary_persona
        session = start_interaction(role=self.role, persona=persona, character=character)
        offers = available_offers(session)
        self.assertNotIn(self.offer, offers)


class ClueRevealHandlerTests(TestCase):
    """Direct handler tests: `run_clue_reveal_offer` grant/deflect/fail-closed paths."""

    def setUp(self) -> None:
        self.character, self.persona, self.roster_entry = _pc_with_roster_entry()
        self.role = NPCRoleFactory(name="Threshold Warden")
        self.entry = CodexEntryFactory()
        self.clue = ClueFactory(target_codex_entry=self.entry, name="Where the Smugglers Land")

    def test_no_check_type_grants_immediately(self) -> None:
        offer = NPCServiceOfferFactory(
            role=self.role, kind=OfferKind.CLUE_REVEAL, label="Ask", is_final=True, check_type=None
        )
        ClueRevealOfferDetailsFactory(offer=offer, clue=self.clue)

        result = run_clue_reveal_offer(offer, self.persona)

        self.assertEqual(result.object_pk, self.clue.pk)
        self.assertTrue(
            CharacterClue.objects.filter(roster_entry=self.roster_entry, clue=self.clue).exists()
        )
        knowledge = CharacterCodexKnowledge.objects.get(
            roster_entry=self.roster_entry, entry=self.entry
        )
        self.assertEqual(knowledge.status, CodexKnowledgeStatus.KNOWN)

    def test_check_success_grants_target(self) -> None:
        check_type = CheckTypeFactory()
        offer = NPCServiceOfferFactory(
            role=self.role,
            kind=OfferKind.CLUE_REVEAL,
            label="Ask",
            is_final=True,
            check_type=check_type,
            check_difficulty=10,
        )
        ClueRevealOfferDetailsFactory(offer=offer, clue=self.clue)

        with mock.patch(
            "world.checks.services.perform_check",
            return_value=SimpleNamespace(success_level=1),
        ):
            result = run_clue_reveal_offer(offer, self.persona)

        self.assertEqual(result.object_pk, self.clue.pk)
        self.assertIn(self.clue.description, result.message)
        self.assertTrue(
            CharacterClue.objects.filter(roster_entry=self.roster_entry, clue=self.clue).exists()
        )
        knowledge = CharacterCodexKnowledge.objects.get(
            roster_entry=self.roster_entry, entry=self.entry
        )
        self.assertEqual(knowledge.status, CodexKnowledgeStatus.KNOWN)

    def test_check_failure_grants_nothing(self) -> None:
        check_type = CheckTypeFactory()
        offer = NPCServiceOfferFactory(
            role=self.role,
            kind=OfferKind.CLUE_REVEAL,
            label="Ask",
            is_final=True,
            check_type=check_type,
            check_difficulty=10,
        )
        ClueRevealOfferDetailsFactory(offer=offer, clue=self.clue)

        with mock.patch(
            "world.checks.services.perform_check",
            return_value=SimpleNamespace(success_level=0),
        ):
            result = run_clue_reveal_offer(offer, self.persona)

        self.assertIsNone(result.object_pk)
        self.assertFalse(
            CharacterClue.objects.filter(roster_entry=self.roster_entry, clue=self.clue).exists()
        )
        self.assertFalse(
            CharacterCodexKnowledge.objects.filter(roster_entry=self.roster_entry).exists()
        )

    def test_no_roster_entry_fails_closed(self) -> None:
        character = CharacterFactory()
        sheet = CharacterSheetFactory(character=character)
        persona = sheet.primary_persona
        offer = NPCServiceOfferFactory(
            role=self.role, kind=OfferKind.CLUE_REVEAL, label="Ask", is_final=True, check_type=None
        )
        ClueRevealOfferDetailsFactory(offer=offer, clue=self.clue)

        result = run_clue_reveal_offer(offer, persona)

        self.assertIsNone(result.object_pk)
        self.assertIn("roster tenure", result.message)
        self.assertFalse(CharacterClue.objects.filter(clue=self.clue).exists())

    def test_dispatch_reaches_clue_reveal_handler(self) -> None:
        offer = NPCServiceOfferFactory(
            role=self.role, kind=OfferKind.CLUE_REVEAL, label="Ask", is_final=True, check_type=None
        )
        ClueRevealOfferDetailsFactory(offer=offer, clue=self.clue)
        result = dispatch_offer_effect(offer, self.persona)
        self.assertEqual(result.kind, OfferKind.CLUE_REVEAL.value)


class ClueRevealJourneyTests(TestCase):
    """Full interaction-loop journey: listing -> resolve -> re-list (spec test seam)."""

    def setUp(self) -> None:
        self.character, self.persona, self.roster_entry = _pc_with_roster_entry()
        self.role = NPCRoleFactory(name="Threshold Warden")
        self.entry = CodexEntryFactory()
        self.clue = ClueFactory(target_codex_entry=self.entry, name="Where the Smugglers Land")
        self.check_type = CheckTypeFactory()
        self.offer = NPCServiceOfferFactory(
            role=self.role,
            kind=OfferKind.CLUE_REVEAL,
            label="Ask about the smugglers",
            is_final=True,
            check_type=self.check_type,
            check_difficulty=10,
        )
        ClueRevealOfferDetailsFactory(offer=self.offer, clue=self.clue)

    def test_success_then_offer_no_longer_listed(self) -> None:
        session = start_interaction(role=self.role, persona=self.persona, character=self.character)
        self.assertIn(self.offer, available_offers(session))

        with mock.patch(
            "world.checks.services.perform_check",
            return_value=SimpleNamespace(success_level=1),
        ):
            result = resolve_offer(session, self.offer)
        self.assertEqual(result.object_pk, self.clue.pk)

        session2 = start_interaction(role=self.role, persona=self.persona, character=self.character)
        self.assertNotIn(self.offer, available_offers(session2))

    def test_failure_leaves_offer_listed_and_grants_nothing(self) -> None:
        session = start_interaction(role=self.role, persona=self.persona, character=self.character)

        with mock.patch(
            "world.checks.services.perform_check",
            return_value=SimpleNamespace(success_level=0),
        ):
            result = resolve_offer(session, self.offer)
        self.assertIsNone(result.object_pk)
        self.assertFalse(
            CharacterClue.objects.filter(roster_entry=self.roster_entry, clue=self.clue).exists()
        )

        # Session closed by the final action; a fresh interaction still lists it —
        # the clue was never granted, so the "already holds it" exclusion never fires.
        session2 = start_interaction(role=self.role, persona=self.persona, character=self.character)
        self.assertIn(self.offer, available_offers(session2))
