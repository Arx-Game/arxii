"""Tests for EncounterCombatHandler (Phase 2 — combat-resolution-loop).

The handler caches an encounter's combat state in a single prefetched
snapshot. Subset reads do list-comps over the cache rather than hitting
the DB again. Mutation services explicitly invalidate.
"""

from __future__ import annotations

from django.test import TestCase

from world.combat.constants import ClashStatus, EncounterStatus
from world.combat.factories import (
    ClashFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
)
from world.combat.handlers import EncounterCombatHandler


class EncounterCombatHandlerCachingTests(TestCase):
    """The handler should prefetch state once and serve subset reads from cache."""

    def setUp(self) -> None:
        super().setUp()
        # Avoid setUpTestData — Evennia DbHolder isn't deepcopy-safe.
        self.encounter = CombatEncounterFactory(round_number=1, status=EncounterStatus.DECLARING)
        self.participant_a = CombatParticipantFactory(encounter=self.encounter)
        self.participant_b = CombatParticipantFactory(encounter=self.encounter)
        self.action_a = CombatRoundActionFactory(participant=self.participant_a, round_number=1)
        self.action_b = CombatRoundActionFactory(participant=self.participant_b, round_number=1)

    def test_state_prefetches_once(self) -> None:
        """Multiple subset reads share one prefetch — no follow-up queries."""
        handler = EncounterCombatHandler(self.encounter)

        # Populate the cache.
        _ = handler._state

        # Subsequent subset reads do not query.
        with self.assertNumQueries(0):
            handler.participants()
            handler.active_clashes()
            handler.pc_actions_for_round(1)
            handler.npc_actions_for_round(1)
            handler.clash_declarations_for_round(1)

    def test_invalidate_drops_cache(self) -> None:
        """After invalidate(), the next read re-queries (i.e. is non-zero)."""
        handler = EncounterCombatHandler(self.encounter)
        _ = handler._state  # populate
        handler.invalidate()

        # After invalidate, the property is not in __dict__.
        self.assertNotIn("_state", handler.__dict__)
        # Reading again should rebuild — at minimum it executes queries.
        with self.assertNumQueries(5):
            _ = handler._state

    def test_pc_actions_for_round_returns_only_that_round(self) -> None:
        """pc_actions_for_round filters by round_number."""
        # Add an action in round 2.
        round2_action = CombatRoundActionFactory(participant=self.participant_a, round_number=2)

        handler = EncounterCombatHandler(self.encounter)
        round1 = handler.pc_actions_for_round(1)
        round2 = handler.pc_actions_for_round(2)

        round1_ids = {a.pk for a in round1}
        round2_ids = {a.pk for a in round2}
        self.assertEqual(round1_ids, {self.action_a.pk, self.action_b.pk})
        self.assertEqual(round2_ids, {round2_action.pk})

    def test_participant_for_sheet_finds_match(self) -> None:
        """participant_for_sheet returns the right participant for a character_sheet."""
        handler = EncounterCombatHandler(self.encounter)
        found = handler.participant_for_sheet(self.participant_a.character_sheet)
        self.assertEqual(found, self.participant_a)

    def test_participant_for_sheet_returns_none_for_unknown(self) -> None:
        """participant_for_sheet returns None when the sheet isn't in this encounter."""
        outside_participant = CombatParticipantFactory()  # different encounter
        handler = EncounterCombatHandler(self.encounter)
        self.assertIsNone(handler.participant_for_sheet(outside_participant.character_sheet))


class EncounterCombatHandlerClashTests(TestCase):
    """Tests for clash-related subset methods on the handler."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory(round_number=2)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        self.active_clash = ClashFactory(
            encounter=self.encounter,
            npc_opponent=self.opponent,
            initiator=self.participant.character_sheet,
            status=ClashStatus.ACTIVE,
        )

    def test_active_clashes_returns_active_only(self) -> None:
        """active_clashes filters by status=ACTIVE."""
        resolved_opponent = CombatOpponentFactory(encounter=self.encounter)
        ClashFactory(
            encounter=self.encounter,
            npc_opponent=resolved_opponent,
            status=ClashStatus.RESOLVED,
        )

        handler = EncounterCombatHandler(self.encounter)
        active = handler.active_clashes()
        self.assertEqual([c.pk for c in active], [self.active_clash.pk])

    def test_principal_clashes_for_returns_initiated_clashes(self) -> None:
        """principal_clashes_for returns clashes the participant initiated."""
        # Another participant + clash they didn't initiate.
        other_participant = CombatParticipantFactory(encounter=self.encounter)

        handler = EncounterCombatHandler(self.encounter)
        principal = handler.principal_clashes_for(self.participant)
        not_principal = handler.principal_clashes_for(other_participant)

        self.assertEqual([c.pk for c in principal], [self.active_clash.pk])
        self.assertEqual(not_principal, [])
