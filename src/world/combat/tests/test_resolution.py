"""Tests for the resolution order service."""

from evennia.utils.test_resources import BaseEvenniaTest

from world.combat.constants import (
    ENTITY_TYPE_NPC,
    ENTITY_TYPE_PC,
    OpponentStatus,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import get_resolution_order
from world.vitals.constants import CharacterStatus


class GetResolutionOrderTest(BaseEvenniaTest):
    """Tests for get_resolution_order."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory()

    def test_covenant_roles_resolve_before_npcs(self) -> None:
        """PC with rank 1 appears before NPC (rank 15)."""
        pc = CombatParticipantFactory(
            encounter=self.encounter,
            base_speed_rank=1,
        )
        npc = CombatOpponentFactory(encounter=self.encounter)

        order = get_resolution_order(self.encounter)

        self.assertEqual(len(order), 2)
        self.assertEqual(order[0], (ENTITY_TYPE_PC, pc))
        self.assertEqual(order[1], (ENTITY_TYPE_NPC, npc))

    def test_no_role_resolves_after_npcs(self) -> None:
        """No-role PC (rank 20) appears after NPC (rank 15)."""
        npc = CombatOpponentFactory(encounter=self.encounter)
        pc = CombatParticipantFactory(
            encounter=self.encounter,
        )

        order = get_resolution_order(self.encounter)

        self.assertEqual(len(order), 2)
        self.assertEqual(order[0], (ENTITY_TYPE_NPC, npc))
        self.assertEqual(order[1], (ENTITY_TYPE_PC, pc))

    def test_speed_modifier_adjusts_rank(self) -> None:
        """Base rank 4 with speed_modifier=-3 (rank 1) before normal rank 4."""
        fast_pc = CombatParticipantFactory(
            encounter=self.encounter,
            base_speed_rank=4,
            speed_modifier=-3,
        )
        normal_pc = CombatParticipantFactory(
            encounter=self.encounter,
            base_speed_rank=4,
        )

        order = get_resolution_order(self.encounter)

        self.assertEqual(len(order), 2)
        self.assertEqual(order[0], (ENTITY_TYPE_PC, fast_pc))
        self.assertEqual(order[1], (ENTITY_TYPE_PC, normal_pc))

    def test_unconscious_pcs_excluded(self) -> None:
        """Unconscious PC not in resolution order."""
        CombatParticipantFactory(
            encounter=self.encounter,
            status=CharacterStatus.UNCONSCIOUS,
        )
        npc = CombatOpponentFactory(encounter=self.encounter)

        order = get_resolution_order(self.encounter)

        self.assertEqual(len(order), 1)
        self.assertEqual(order[0], (ENTITY_TYPE_NPC, npc))

    def test_dead_pcs_excluded(self) -> None:
        """Dead PC not in resolution order."""
        CombatParticipantFactory(
            encounter=self.encounter,
            status=CharacterStatus.DEAD,
        )
        npc = CombatOpponentFactory(encounter=self.encounter)

        order = get_resolution_order(self.encounter)

        self.assertEqual(len(order), 1)
        self.assertEqual(order[0], (ENTITY_TYPE_NPC, npc))

    def test_dying_pc_with_final_round_included(self) -> None:
        """Dying PC with dying_final_round=True IS included."""
        dying_pc = CombatParticipantFactory(
            encounter=self.encounter,
            base_speed_rank=1,
            status=CharacterStatus.DYING,
            dying_final_round=True,
        )

        order = get_resolution_order(self.encounter)

        self.assertEqual(len(order), 1)
        self.assertEqual(order[0], (ENTITY_TYPE_PC, dying_pc))

    def test_dying_pc_without_final_round_excluded(self) -> None:
        """Dying PC with dying_final_round=False NOT included."""
        CombatParticipantFactory(
            encounter=self.encounter,
            status=CharacterStatus.DYING,
            dying_final_round=False,
        )

        order = get_resolution_order(self.encounter)

        self.assertEqual(len(order), 0)

    def test_defeated_opponents_excluded(self) -> None:
        """Defeated opponent not in resolution order."""
        CombatOpponentFactory(
            encounter=self.encounter,
            status=OpponentStatus.DEFEATED,
        )
        pc = CombatParticipantFactory(
            encounter=self.encounter,
            base_speed_rank=1,
        )

        order = get_resolution_order(self.encounter)

        self.assertEqual(len(order), 1)
        self.assertEqual(order[0], (ENTITY_TYPE_PC, pc))

    def test_multiple_roles_sort_correctly(self) -> None:
        """Rank 1, 6, 10 — verify resolution order."""
        slowest = CombatParticipantFactory(
            encounter=self.encounter,
            base_speed_rank=10,
        )
        fastest = CombatParticipantFactory(
            encounter=self.encounter,
            base_speed_rank=1,
        )
        middle = CombatParticipantFactory(
            encounter=self.encounter,
            base_speed_rank=6,
        )

        order = get_resolution_order(self.encounter)

        self.assertEqual(len(order), 3)
        self.assertEqual(order[0], (ENTITY_TYPE_PC, fastest))
        self.assertEqual(order[1], (ENTITY_TYPE_PC, middle))
        self.assertEqual(order[2], (ENTITY_TYPE_PC, slowest))

    def test_empty_encounter(self) -> None:
        """No participants or opponents returns empty list."""
        order = get_resolution_order(self.encounter)

        self.assertEqual(order, [])
