"""Tests for ClashStateSerializer contributors + side_favored fields (Phase 7)."""

from __future__ import annotations

from django.test import TestCase

from world.combat.factories import (
    ClashContributionFactory,
    ClashFactory,
    ClashRoundFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.serializers import ClashStateSerializer


class ClashStateSerializerContributorsTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.opponent = CombatOpponentFactory(encounter=self.encounter, name="Pyromancer")
        self.clash = ClashFactory(
            encounter=self.encounter,
            npc_opponent=self.opponent,
            initiator=self.participant.character_sheet,
            progress=0,
            pc_win_threshold=20,
            npc_win_threshold=-20,
        )

    def test_empty_contributors_when_no_rounds(self) -> None:
        data = ClashStateSerializer(self.clash).data
        self.assertEqual(data["contributors"], [])

    def test_contributors_aggregate_across_rounds(self) -> None:
        clash_round_1 = ClashRoundFactory(clash=self.clash, round_number=1)
        clash_round_2 = ClashRoundFactory(clash=self.clash, round_number=2)
        ClashContributionFactory(
            clash_round=clash_round_1,
            character=self.participant.character_sheet,
            progress_delta=3,
            anima_committed=2,
        )
        ClashContributionFactory(
            clash_round=clash_round_2,
            character=self.participant.character_sheet,
            progress_delta=4,
            anima_committed=1,
        )
        data = ClashStateSerializer(self.clash).data
        self.assertEqual(len(data["contributors"]), 1)
        contrib = data["contributors"][0]
        self.assertEqual(contrib["progress_delta"], 7)
        self.assertEqual(contrib["anima"], 3)


class ClashStateSerializerSideFavoredTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory()
        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        self.clash = ClashFactory(
            encounter=self.encounter,
            npc_opponent=self.opponent,
            pc_win_threshold=20,
            npc_win_threshold=-20,
        )

    def test_even_at_start(self) -> None:
        self.clash.progress = 0
        data = ClashStateSerializer(self.clash).data
        self.assertEqual(data["side_favored"], "EVEN")

    def test_pc_favored_near_threshold(self) -> None:
        self.clash.progress = 16  # 80% of 20
        data = ClashStateSerializer(self.clash).data
        self.assertEqual(data["side_favored"], "PC")

    def test_npc_favored_near_threshold(self) -> None:
        self.clash.progress = -16  # 80% of -20
        data = ClashStateSerializer(self.clash).data
        self.assertEqual(data["side_favored"], "NPC")
