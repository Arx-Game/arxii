"""Tests for the resolution order service."""

from django.test import TestCase, tag

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
from world.conditions.constants import FoundationalCapability
from world.conditions.factories import (
    BleedingOutConditionFactory,
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionStageFactory,
    UnconsciousConditionFactory,
)
from world.conditions.services import apply_condition
from world.covenants.factories import CovenantRoleFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.models import CharacterVitals


class GetResolutionOrderTest(TestCase):
    """Tests for get_resolution_order."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory()

    def test_covenant_roles_resolve_before_npcs(self) -> None:
        """PC with rank 1 appears before NPC (rank 15)."""
        pc = CombatParticipantFactory(
            encounter=self.encounter,
            covenant_role=CovenantRoleFactory(speed_rank=1),
        )
        CharacterVitals.objects.create(
            character_sheet=pc.character_sheet,
            health=100,
            max_health=100,
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
        CharacterVitals.objects.create(
            character_sheet=pc.character_sheet,
            health=100,
            max_health=100,
        )

        order = get_resolution_order(self.encounter)

        self.assertEqual(len(order), 2)
        self.assertEqual(order[0], (ENTITY_TYPE_NPC, npc))
        self.assertEqual(order[1], (ENTITY_TYPE_PC, pc))

    def test_unconscious_pcs_excluded(self) -> None:
        """Unconscious PC (awareness 0 → cannot act) not in resolution order."""
        pc = CombatParticipantFactory(
            encounter=self.encounter,
        )
        CharacterVitals.objects.create(
            character_sheet=pc.character_sheet,
            health=100,
            max_health=100,
        )
        # Unconscious zeroes the foundational AWARENESS capability → can_act False.
        awareness = CapabilityTypeFactory(name=FoundationalCapability.AWARENESS, innate_baseline=1)
        unconscious = UnconsciousConditionFactory()
        ConditionCapabilityEffectFactory(condition=unconscious, capability=awareness, value=-100)
        apply_condition(target=pc.character_sheet.character, condition=unconscious)
        npc = CombatOpponentFactory(encounter=self.encounter)

        order = get_resolution_order(self.encounter)

        self.assertEqual(len(order), 1)
        self.assertEqual(order[0], (ENTITY_TYPE_NPC, npc))

    def test_dead_pcs_excluded(self) -> None:
        """Dead PC (life_state=DEAD) not in resolution order."""
        pc = CombatParticipantFactory(
            encounter=self.encounter,
        )
        CharacterVitals.objects.create(
            character_sheet=pc.character_sheet,
            health=0,
            max_health=100,
            life_state=CharacterLifeState.DEAD,
        )
        npc = CombatOpponentFactory(encounter=self.encounter)

        order = get_resolution_order(self.encounter)

        self.assertEqual(len(order), 1)
        self.assertEqual(order[0], (ENTITY_TYPE_NPC, npc))

    @tag("postgres")
    def test_dying_conscious_pc_included(self) -> None:
        """A dying-but-conscious PC (Bleeding-Out, awareness intact) IS included.

        Bleeding-Out does not impair awareness, so can_act is True and the PC
        keeps acting — replacing the old DYING + dying_final_round gate.
        Bleeding-Out is progressive → apply_condition uses PG DISTINCT ON.
        """
        CapabilityTypeFactory(name=FoundationalCapability.AWARENESS, innate_baseline=1)
        dying_pc = CombatParticipantFactory(
            encounter=self.encounter,
            covenant_role=CovenantRoleFactory(speed_rank=1),
        )
        CharacterVitals.objects.create(
            character_sheet=dying_pc.character_sheet,
            health=10,
            max_health=100,
            life_state=CharacterLifeState.ALIVE,
        )
        bleed_out = BleedingOutConditionFactory()
        ConditionStageFactory(
            condition=bleed_out, stage_order=1, name="Bleeding", rounds_to_next=None
        )
        apply_condition(target=dying_pc.character_sheet.character, condition=bleed_out)

        order = get_resolution_order(self.encounter)

        self.assertEqual(len(order), 1)
        self.assertEqual(order[0], (ENTITY_TYPE_PC, dying_pc))

    def test_defeated_opponents_excluded(self) -> None:
        """Defeated opponent not in resolution order."""
        CombatOpponentFactory(
            encounter=self.encounter,
            status=OpponentStatus.DEFEATED,
        )
        pc = CombatParticipantFactory(
            encounter=self.encounter,
            covenant_role=CovenantRoleFactory(speed_rank=1),
        )
        CharacterVitals.objects.create(
            character_sheet=pc.character_sheet,
            health=100,
            max_health=100,
        )

        order = get_resolution_order(self.encounter)

        self.assertEqual(len(order), 1)
        self.assertEqual(order[0], (ENTITY_TYPE_PC, pc))

    def test_multiple_roles_sort_correctly(self) -> None:
        """Rank 1, 6, 10 — verify resolution order."""
        slowest = CombatParticipantFactory(
            encounter=self.encounter,
            covenant_role=CovenantRoleFactory(speed_rank=10),
        )
        CharacterVitals.objects.create(
            character_sheet=slowest.character_sheet,
            health=100,
            max_health=100,
        )
        fastest = CombatParticipantFactory(
            encounter=self.encounter,
            covenant_role=CovenantRoleFactory(speed_rank=1),
        )
        CharacterVitals.objects.create(
            character_sheet=fastest.character_sheet,
            health=100,
            max_health=100,
        )
        middle = CombatParticipantFactory(
            encounter=self.encounter,
            covenant_role=CovenantRoleFactory(speed_rank=6),
        )
        CharacterVitals.objects.create(
            character_sheet=middle.character_sheet,
            health=100,
            max_health=100,
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
